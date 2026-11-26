"""Spillback-aware corridor orchestrator and closed-loop controller for AegisFlow.

Evaluates junctions in upstream-to-downstream order to coordinate emergency
vehicle green waves, proactive queue flushes, upstream spillback metering,
and post-EV cross-street recovery. All actions remain strictly advisory until
verified by DeterministicSafetyShield.
"""

from orchestrator.config import OrchestratorConfig
from predictor.forecaster import SpillbackPredictor
from safety_shield.shield import DeterministicSafetyShield
from schemas.contracts import (
    ControlActionType,
    JunctionID,
    JunctionStatePacket,
    ProposedControlAction,
    SignalPhase,
    SpillbackForecast,
    VerifiedSignalCommand,
)

_CLEARANCE_NEXT_PHASE: dict[SignalPhase, SignalPhase] = {
    SignalPhase.NS_YELLOW: SignalPhase.ALL_RED_TO_EW,
    SignalPhase.ALL_RED_TO_EW: SignalPhase.EW_GREEN,
    SignalPhase.EW_YELLOW: SignalPhase.ALL_RED_TO_NS,
    SignalPhase.ALL_RED_TO_NS: SignalPhase.NS_GREEN,
}
_CLEARANCE_REQUIRED_S: dict[SignalPhase, float] = {
    SignalPhase.NS_YELLOW: 3.0,
    SignalPhase.EW_YELLOW: 3.0,
    SignalPhase.ALL_RED_TO_EW: 2.0,
    SignalPhase.ALL_RED_TO_NS: 2.0,
}


class CorridorOrchestrator:
    """Spillback-aware multi-junction signal strategy proposer (advisory only)."""

    def __init__(self, config: OrchestratorConfig | None = None) -> None:
        """Initialize orchestrator configuration and per-junction EV clearance state."""
        self.config: OrchestratorConfig = config or OrchestratorConfig()
        self.ev_recently_cleared: dict[JunctionID, bool] = {
            jid: False for jid in JunctionID
        }
        self._ev_was_active: dict[JunctionID, bool] = {
            jid: False for jid in JunctionID
        }

    def _update_ev_clearance_state(
        self,
        junction_id: JunctionID,
        state: JunctionStatePacket,
        forecast: SpillbackForecast,
    ) -> None:
        """Track EV arrival and exit events to trigger post-EV recovery."""
        ev_present = state.ev_detected or forecast.predicted_ev_eta_s is not None
        was_active = self._ev_was_active.get(junction_id, False)

        if state.ev_detected:
            self.ev_recently_cleared[junction_id] = False
        elif was_active and not ev_present:
            self.ev_recently_cleared[junction_id] = True
        elif (
            self.ev_recently_cleared.get(junction_id, False)
            and state.active_phase == SignalPhase.NS_GREEN
            and state.phase_elapsed_s >= 10.0
        ):
            self.ev_recently_cleared[junction_id] = False

        self._ev_was_active[junction_id] = state.ev_detected or (
            forecast.predicted_ev_eta_s is not None
            and forecast.predicted_ev_eta_s <= self.config.ev_flush_window_max_s
        )

    def _effective_ev_eta(
        self,
        state: JunctionStatePacket,
        forecast: SpillbackForecast,
    ) -> float | None:
        """Return the best estimate of EV arrival time (seconds) at this junction."""
        if state.ev_detected:
            if state.ev_eta_s is not None:
                return state.ev_eta_s
            if forecast.predicted_ev_eta_s is not None:
                return forecast.predicted_ev_eta_s
            return 5.0
        return forecast.predicted_ev_eta_s

    def _clearance_action(
        self,
        state: JunctionStatePacket,
        reason_prefix: str,
    ) -> ProposedControlAction:
        """Respect an active yellow/all-red interval before requesting green changes."""
        active = state.active_phase
        required_s = _CLEARANCE_REQUIRED_S[active]
        if state.phase_elapsed_s >= required_s:
            next_phase = _CLEARANCE_NEXT_PHASE[active]
            duration = (
                2.0
                if next_phase in (SignalPhase.ALL_RED_TO_EW, SignalPhase.ALL_RED_TO_NS)
                else 15.0
            )
            return ProposedControlAction(
                junction_id=state.junction_id,
                timestamp=state.timestamp,
                target_phase=next_phase,
                action_type=ControlActionType.HOLD,
                requested_duration_s=duration,
                reason=f"{reason_prefix}: advancing clearance {active} -> {next_phase}.",
                priority_score=0.65,
            )

        remaining_s = max(1.0, round(required_s - state.phase_elapsed_s, 2))
        return ProposedControlAction(
            junction_id=state.junction_id,
            timestamp=state.timestamp,
            target_phase=active,
            action_type=ControlActionType.HOLD,
            requested_duration_s=remaining_s,
            reason=f"{reason_prefix}: completing mandatory clearance {active}.",
            priority_score=0.60,
        )

    def _decide_single_junction(
        self,
        junction_id: JunctionID,
        downstream_id: JunctionID | None,
        states: dict[JunctionID, JunctionStatePacket],
        forecasts: dict[JunctionID, SpillbackForecast],
        corridor_ev_active: bool,
    ) -> ProposedControlAction:
        """Compute the prioritized advisory control action for one junction."""
        state = states[junction_id]
        forecast = forecasts[junction_id]
        eta = self._effective_ev_eta(state, forecast)
        ev_at_or_approaching = state.ev_detected or eta is not None

        downstream_forecast = (
            forecasts.get(downstream_id) if downstream_id is not None else None
        )
        downstream_spillback = downstream_forecast is not None and (
            downstream_forecast.spillback_imminent
            or downstream_forecast.spillback_risk_index
            >= self.config.metering_spillback_trigger
        )

        # 1. Upstream Metering (UPSTREAM_METERING)
        if downstream_spillback and not ev_at_or_approaching:
            assert downstream_id is not None and downstream_forecast is not None
            risk = downstream_forecast.spillback_risk_index
            if state.active_phase in _CLEARANCE_NEXT_PHASE:
                return self._clearance_action(
                    state,
                    f"Upstream Metering prep for {downstream_id} (risk {risk:.2f})",
                )
            priority = round(min(0.92, 0.80 + 0.08 * min(1.5, risk)), 3)
            action_verb = (
                "holding"
                if state.active_phase == SignalPhase.NS_GREEN
                else "switching to"
            )
            return ProposedControlAction(
                junction_id=junction_id,
                timestamp=state.timestamp,
                target_phase=SignalPhase.NS_GREEN,
                action_type=ControlActionType.UPSTREAM_METERING,
                requested_duration_s=15.0,
                reason=(
                    f"Upstream Metering: {downstream_id} spillback risk {risk:.2f}; "
                    f"{action_verb} NS_GREEN at {junction_id} to throttle inflow."
                ),
                priority_score=priority,
            )

        # 2. Green Extension (GREEN_EXTENSION)
        if (
            eta is not None
            and eta <= self.config.ev_extension_window_s
            and state.active_phase == SignalPhase.EW_GREEN
        ):
            ext_duration = round(max(10.0, min(30.0, eta + 8.0)), 2)
            priority = round(max(0.90, min(1.0, 1.0 - 0.004 * eta)), 3)
            return ProposedControlAction(
                junction_id=junction_id,
                timestamp=state.timestamp,
                target_phase=SignalPhase.EW_GREEN,
                action_type=ControlActionType.GREEN_EXTENSION,
                requested_duration_s=ext_duration,
                reason=(
                    f"Green Extension: EV ETA {eta:.1f}s at {junction_id}; "
                    f"extending EW_GREEN for {ext_duration:.0f}s."
                ),
                priority_score=priority,
            )

        # 3. Proactive Queue Flush (RED_TRUNCATION)
        ev_in_flush_window = (
            eta is not None
            and (
                self.config.ev_flush_window_min_s
                <= eta
                <= self.config.ev_flush_window_max_s
                or eta < self.config.ev_flush_window_min_s
            )
        )
        local_spillback = (
            forecast.spillback_imminent
            or forecast.spillback_risk_index >= self.config.metering_spillback_trigger
        )
        if (ev_in_flush_window or local_spillback) and (
            state.active_phase != SignalPhase.EW_GREEN
        ):
            if state.active_phase in (
                SignalPhase.NS_YELLOW,
                SignalPhase.ALL_RED_TO_EW,
            ):
                return self._clearance_action(
                    state,
                    f"Proactive Queue Flush transition at {junction_id}",
                )

            high_standing_queue = (
                state.spatial_occupancy_ratio >= self.config.flush_occupancy_trigger
                or forecast.predicted_occupancy_ratio
                >= self.config.flush_occupancy_trigger
            )
            flush_duration = 25.0 if high_standing_queue else 15.0
            if eta is not None:
                priority = round(max(0.85, min(0.98, 0.96 - 0.002 * eta)), 3)
                reason = (
                    f"Proactive Queue Flush: EV ETA {eta:.1f}s at {junction_id} "
                    f"& spillback risk {forecast.spillback_risk_index:.2f}."
                )
            else:
                priority = round(
                    max(0.85, min(0.95, 0.85 + 0.06 * forecast.spillback_risk_index)),
                    3,
                )
                reason = (
                    f"Proactive Queue Flush: {junction_id} spillback risk "
                    f"{forecast.spillback_risk_index:.2f} requires arterial discharge."
                )

            return ProposedControlAction(
                junction_id=junction_id,
                timestamp=state.timestamp,
                target_phase=SignalPhase.EW_GREEN,
                action_type=ControlActionType.RED_TRUNCATION,
                requested_duration_s=flush_duration,
                reason=reason,
                priority_score=priority,
            )

        # 4. Post-EV Recovery & Max-Pressure Equilibrium (RECOVERY / HOLD)
        if state.active_phase in _CLEARANCE_NEXT_PHASE:
            return self._clearance_action(
                state,
                f"Equilibrium clearance at {junction_id}",
            )

        arterial_pressure = (
            0.5 * state.queue_length_m + 0.5 * forecast.predicted_queue_length_m
        ) / 10.0
        cross_street_pressure = state.phase_elapsed_s * (
            0.8 + 0.4 * min(1.5, state.inflow_rate_vps)
        )
        recently_cleared = self.ev_recently_cleared.get(junction_id, False)
        if recently_cleared:
            cross_street_pressure += self.config.max_pressure_switch_threshold + 10.0

        pressure_gap = cross_street_pressure - arterial_pressure
        if (
            not ev_at_or_approaching
            and state.active_phase != SignalPhase.NS_GREEN
            and (
                recently_cleared
                or pressure_gap >= self.config.max_pressure_switch_threshold
            )
        ):
            reason = (
                f"Post-EV Recovery: EV cleared {junction_id}; restoring cross-street NS_GREEN."
                if recently_cleared
                else (
                    f"Max-Pressure Recovery: cross-street pressure ({cross_street_pressure:.1f}) "
                    f"exceeds arterial ({arterial_pressure:.1f}) at {junction_id}."
                )
            )
            return ProposedControlAction(
                junction_id=junction_id,
                timestamp=state.timestamp,
                target_phase=SignalPhase.NS_GREEN,
                action_type=ControlActionType.RECOVERY,
                requested_duration_s=20.0,
                reason=reason,
                priority_score=0.72 if recently_cleared else 0.62,
            )

        corridor_tag = "corridor EV active" if corridor_ev_active else "normal flow"
        return ProposedControlAction(
            junction_id=junction_id,
            timestamp=state.timestamp,
            target_phase=state.active_phase,
            action_type=ControlActionType.HOLD,
            requested_duration_s=15.0,
            reason=(
                f"Hold {state.active_phase} at {junction_id} ({corridor_tag}, "
                f"spillback risk {forecast.spillback_risk_index:.2f})."
            ),
            priority_score=0.45,
        )

    def decide_corridor(
        self,
        states: dict[JunctionID, JunctionStatePacket],
        forecasts: dict[JunctionID, SpillbackForecast],
    ) -> dict[JunctionID, ProposedControlAction]:
        """Evaluate all corridor junctions in topological order and propose actions."""
        corridor_ev_active = any(s.ev_detected for s in states.values()) or any(
            f.predicted_ev_eta_s is not None for f in forecasts.values()
        )

        order = self.config.corridor_order
        proposals: dict[JunctionID, ProposedControlAction] = {}
        for idx, junction_id in enumerate(order):
            if junction_id not in states or junction_id not in forecasts:
                continue
            self._update_ev_clearance_state(
                junction_id, states[junction_id], forecasts[junction_id]
            )
            downstream_id = order[idx + 1] if idx + 1 < len(order) else None
            proposals[junction_id] = self._decide_single_junction(
                junction_id=junction_id,
                downstream_id=downstream_id,
                states=states,
                forecasts=forecasts,
                corridor_ev_active=corridor_ev_active,
            )

        return proposals


class AegisFlowController:
    """Closed-loop wrapper combining Predictor, Orchestrator, and Safety Shield."""

    def __init__(
        self,
        predictor: SpillbackPredictor | None = None,
        orchestrator: CorridorOrchestrator | None = None,
        safety_shield: DeterministicSafetyShield | None = None,
    ) -> None:
        """Initialize the full intelligence + deterministic safety pipeline."""
        self.predictor: SpillbackPredictor = predictor or SpillbackPredictor()
        self.orchestrator: CorridorOrchestrator = orchestrator or CorridorOrchestrator()
        self.safety_shield: DeterministicSafetyShield = (
            safety_shield or DeterministicSafetyShield()
        )

    def step(
        self,
        corridor_states: dict[JunctionID, JunctionStatePacket],
    ) -> tuple[
        dict[JunctionID, SpillbackForecast],
        dict[JunctionID, ProposedControlAction],
        dict[JunctionID, VerifiedSignalCommand],
    ]:
        """Execute one closed-loop forecast -> orchestrate -> verify step."""
        self.predictor.update_calibration(corridor_states)
        forecasts = self.predictor.predict_corridor(corridor_states)
        proposals = self.orchestrator.decide_corridor(corridor_states, forecasts)
        commands = {
            junction_id: self.safety_shield.verify(
                corridor_states[junction_id],
                proposals[junction_id],
            )
            for junction_id in proposals
        }
        return forecasts, proposals, commands
