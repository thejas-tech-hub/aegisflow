"""Conventional isolated Emergency Vehicle Preemption (Baseline) controller.

Models legacy localized EVP with fixed-time signal cycling and blind local
preemption triggered only when an EV is physically detected within 110m of a
single junction. Every proposed command still passes through DeterministicSafetyShield
to guarantee a fair municipal safety comparison against AegisFlow.
"""

from safety_shield.shield import DeterministicSafetyShield
from schemas.contracts import (
    ControlActionType,
    JunctionID,
    JunctionStatePacket,
    ProposedControlAction,
    SignalPhase,
    VerifiedSignalCommand,
)

_FIXED_GREEN_DURATION_S = 30.0
_FIXED_YELLOW_DURATION_S = 3.0
_FIXED_ALL_RED_DURATION_S = 2.0
_LOCAL_EVP_TRIGGER_DISTANCE_M = 110.0

_NEXT_FIXED_PHASE: dict[SignalPhase, SignalPhase] = {
    SignalPhase.EW_GREEN: SignalPhase.EW_YELLOW,
    SignalPhase.EW_YELLOW: SignalPhase.ALL_RED_TO_NS,
    SignalPhase.ALL_RED_TO_NS: SignalPhase.NS_GREEN,
    SignalPhase.NS_GREEN: SignalPhase.NS_YELLOW,
    SignalPhase.NS_YELLOW: SignalPhase.ALL_RED_TO_EW,
    SignalPhase.ALL_RED_TO_EW: SignalPhase.EW_GREEN,
}
_FIXED_PHASE_LIMIT_S: dict[SignalPhase, float] = {
    SignalPhase.EW_GREEN: _FIXED_GREEN_DURATION_S,
    SignalPhase.EW_YELLOW: _FIXED_YELLOW_DURATION_S,
    SignalPhase.ALL_RED_TO_NS: _FIXED_ALL_RED_DURATION_S,
    SignalPhase.NS_GREEN: _FIXED_GREEN_DURATION_S,
    SignalPhase.NS_YELLOW: _FIXED_YELLOW_DURATION_S,
    SignalPhase.ALL_RED_TO_EW: _FIXED_ALL_RED_DURATION_S,
}


class IsolatedEVPController:
    """Legacy isolated local-only EVP controller wrapped with Safety Shield."""

    def __init__(
        self,
        safety_shield: DeterministicSafetyShield | None = None,
        trigger_distance_m: float = _LOCAL_EVP_TRIGGER_DISTANCE_M,
    ) -> None:
        """Initialize fixed-time local EVP controller and municipal shield."""
        self.safety_shield: DeterministicSafetyShield = (
            safety_shield or DeterministicSafetyShield()
        )
        self.trigger_distance_m = trigger_distance_m

    def _propose_for_junction(
        self, state: JunctionStatePacket
    ) -> ProposedControlAction:
        """Propose a localized fixed-time or short-range EVP signal action."""
        active = state.active_phase
        local_ev_triggered = (
            state.ev_detected
            and state.ev_distance_m is not None
            and state.ev_distance_m <= self.trigger_distance_m
        )

        if local_ev_triggered:
            if active == SignalPhase.EW_GREEN:
                return ProposedControlAction(
                    junction_id=state.junction_id,
                    timestamp=state.timestamp,
                    target_phase=SignalPhase.EW_GREEN,
                    action_type=ControlActionType.GREEN_EXTENSION,
                    requested_duration_s=20.0,
                    reason=(
                        f"Isolated EVP: local EV at {state.ev_distance_m:.1f}m "
                        f"<= {self.trigger_distance_m:.0f}m; holding EW_GREEN."
                    ),
                    priority_score=0.90,
                )
            if active in (SignalPhase.NS_YELLOW, SignalPhase.ALL_RED_TO_EW):
                limit = _FIXED_PHASE_LIMIT_S[active]
                if state.phase_elapsed_s >= limit:
                    next_phase = _NEXT_FIXED_PHASE[active]
                    dur = 20.0 if next_phase == SignalPhase.EW_GREEN else 2.0
                    return ProposedControlAction(
                        junction_id=state.junction_id,
                        timestamp=state.timestamp,
                        target_phase=next_phase,
                        action_type=ControlActionType.HOLD,
                        requested_duration_s=dur,
                        reason=f"Isolated EVP: advancing clearance {active} -> {next_phase}.",
                        priority_score=0.85,
                    )
                return ProposedControlAction(
                    junction_id=state.junction_id,
                    timestamp=state.timestamp,
                    target_phase=active,
                    action_type=ControlActionType.HOLD,
                    requested_duration_s=max(1.0, limit - state.phase_elapsed_s),
                    reason=f"Isolated EVP: completing clearance {active}.",
                    priority_score=0.80,
                )

            return ProposedControlAction(
                junction_id=state.junction_id,
                timestamp=state.timestamp,
                target_phase=SignalPhase.EW_GREEN,
                action_type=ControlActionType.RED_TRUNCATION,
                requested_duration_s=20.0,
                reason=(
                    f"Isolated EVP: reactive preemption for EV at "
                    f"{state.ev_distance_m:.1f}m."
                ),
                priority_score=0.88,
            )

        # Standard fixed-time cycle when no local EV is within trigger range.
        phase_limit = _FIXED_PHASE_LIMIT_S[active]
        if state.phase_elapsed_s >= phase_limit:
            next_phase = _NEXT_FIXED_PHASE[active]
            next_duration = _FIXED_PHASE_LIMIT_S[next_phase]
            return ProposedControlAction(
                junction_id=state.junction_id,
                timestamp=state.timestamp,
                target_phase=next_phase,
                action_type=ControlActionType.RECOVERY,
                requested_duration_s=next_duration,
                reason=f"Fixed-time transition {active} -> {next_phase}.",
                priority_score=0.40,
            )

        return ProposedControlAction(
            junction_id=state.junction_id,
            timestamp=state.timestamp,
            target_phase=active,
            action_type=ControlActionType.HOLD,
            requested_duration_s=max(10.0, phase_limit - state.phase_elapsed_s)
            if active in (SignalPhase.EW_GREEN, SignalPhase.NS_GREEN)
            else max(1.0, phase_limit - state.phase_elapsed_s),
            reason=f"Fixed-time hold on {active} ({state.phase_elapsed_s:.0f}s/{phase_limit:.0f}s).",
            priority_score=0.30,
        )

    def step(
        self,
        corridor_states: dict[JunctionID, JunctionStatePacket],
    ) -> tuple[
        dict[JunctionID, ProposedControlAction],
        dict[JunctionID, VerifiedSignalCommand],
    ]:
        """Evaluate fixed-time / local EVP logic and verify via Safety Shield."""
        proposals: dict[JunctionID, ProposedControlAction] = {}
        commands: dict[JunctionID, VerifiedSignalCommand] = {}
        for jid in JunctionID:
            if jid not in corridor_states:
                continue
            state = corridor_states[jid]
            proposal = self._propose_for_junction(state)
            proposals[jid] = proposal
            commands[jid] = self.safety_shield.verify(state, proposal)
        return proposals, commands
