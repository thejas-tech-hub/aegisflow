"""Physics-informed Cell Transmission & shockwave spillback predictor for AegisFlow.

Combines upstream platoon propagation with travel-delay attenuation, phase-aware
saturation discharge, rolling queue-velocity estimation, EV shockwave ETA
propagation, and an online residual bias calibration hook.
"""

from collections import deque

from predictor.config import PredictorConfig
from schemas.contracts import (
    JunctionID,
    JunctionStatePacket,
    SignalPhase,
    SpillbackForecast,
    VehicleMix,
)

_MIN_TRAVEL_SPEED_MPS = 2.0
_MIN_EV_SPEED_MPS = 5.0
_MAX_EV_SPEED_MPS = 16.0
_DEFAULT_EV_SPEED_MPS = 12.0
_TURNING_INFLOW_SHARE = 0.35


def _mean_pcu_per_vehicle(mix: VehicleMix) -> float:
    """Compute average Indian PCU equivalence factor across the observed mix."""
    total_vehicles = (
        mix.motorcycles
        + mix.auto_rickshaws
        + mix.cars
        + mix.buses_trucks
        + mix.emergency_vehicles
    )
    if total_vehicles <= 0:
        return 1.0
    total_pcu = (
        0.5 * mix.motorcycles
        + 0.8 * mix.auto_rickshaws
        + 1.0 * mix.cars
        + 2.5 * mix.buses_trucks
        + 1.5 * mix.emergency_vehicles
    )
    return total_pcu / total_vehicles


class ResidualCalibrationHook:
    """Lightweight online EMA + ridge bias corrector for queue-length residuals."""

    def __init__(
        self,
        ema_alpha: float = 0.25,
        ridge_penalty: float = 0.05,
        max_abs_bias_m: float = 45.0,
        timestamp_tolerance_s: float = 2.0,
    ) -> None:
        """Initialize per-junction bias weights and pending forecast buffers."""
        self.ema_alpha = ema_alpha
        self.ridge_penalty = ridge_penalty
        self.max_abs_bias_m = max_abs_bias_m
        self.timestamp_tolerance_s = timestamp_tolerance_s
        self.bias_m: dict[JunctionID, float] = {j: 0.0 for j in JunctionID}
        self.update_counts: dict[JunctionID, int] = {j: 0 for j in JunctionID}
        self.last_residuals_m: dict[JunctionID, float] = {j: 0.0 for j in JunctionID}
        self._pending_forecasts: dict[JunctionID, deque[tuple[float, float]]] = {
            j: deque(maxlen=120) for j in JunctionID
        }

    def record_prediction(
        self,
        junction_id: JunctionID,
        target_timestamp_s: float,
        predicted_queue_length_m: float,
    ) -> None:
        """Store a forecast so it can be scored when future ground truth arrives."""
        self._pending_forecasts[junction_id].append(
            (target_timestamp_s, predicted_queue_length_m)
        )

    def get_bias(self, junction_id: JunctionID) -> float:
        """Return the current learned residual bias offset (meters) for a junction."""
        return self.bias_m.get(junction_id, 0.0)

    def update_calibration(
        self,
        actual_states: dict[JunctionID, JunctionStatePacket],
    ) -> dict[JunctionID, float]:
        """Update EMA/ridge bias weights from newly observed junction queue lengths."""
        for junction_id, actual in actual_states.items():
            pending = self._pending_forecasts[junction_id]
            if not pending:
                continue

            matched_pred: float | None = None
            best_diff = self.timestamp_tolerance_s + 1.0
            remaining: deque[tuple[float, float]] = deque(maxlen=120)

            for target_ts, pred_q in pending:
                diff = abs(actual.timestamp - target_ts)
                if diff <= self.timestamp_tolerance_s and diff < best_diff:
                    best_diff = diff
                    matched_pred = pred_q
                elif target_ts > actual.timestamp - self.timestamp_tolerance_s:
                    remaining.append((target_ts, pred_q))

            self._pending_forecasts[junction_id] = remaining
            if matched_pred is None:
                continue

            residual = actual.queue_length_m - matched_pred
            prev_bias = self.bias_m[junction_id]
            shrunk_bias = prev_bias * (1.0 - self.ridge_penalty)
            updated_bias = (1.0 - self.ema_alpha) * shrunk_bias + (
                self.ema_alpha * residual
            )
            clamped_bias = max(
                -self.max_abs_bias_m, min(self.max_abs_bias_m, updated_bias)
            )
            self.bias_m[junction_id] = round(clamped_bias, 4)
            self.last_residuals_m[junction_id] = round(residual, 4)
            self.update_counts[junction_id] += 1

        return dict(self.bias_m)


class SpillbackPredictor:
    """Physics-informed multi-junction queue and spillback forecaster."""

    def __init__(
        self,
        config: PredictorConfig | None = None,
        calibration_hook: ResidualCalibrationHook | None = None,
    ) -> None:
        """Initialize predictor state buffers, topology, and calibration hook."""
        self.config: PredictorConfig = config or PredictorConfig()
        self.calibration: ResidualCalibrationHook = (
            calibration_hook or ResidualCalibrationHook()
        )
        self.history: dict[JunctionID, deque[JunctionStatePacket]] = {
            junction_id: deque(maxlen=self.config.history_window)
            for junction_id in JunctionID
        }
        self._upstream_map: dict[JunctionID, JunctionID | None] = (
            self._build_reverse_topology()
        )

    def _build_reverse_topology(self) -> dict[JunctionID, JunctionID | None]:
        """Invert upstream->downstream topology to lookup each junction's feeder."""
        reverse: dict[JunctionID, JunctionID | None] = {j: None for j in JunctionID}
        for upstream_id, downstream_id in self.config.corridor_topology.items():
            if downstream_id is not None:
                reverse[downstream_id] = upstream_id
        return reverse

    def _record_state(self, state: JunctionStatePacket) -> None:
        """Append a state snapshot to the bounded junction history without duplicates."""
        buf = self.history[state.junction_id]
        if buf and buf[-1].timestamp == state.timestamp:
            buf[-1] = state
            return
        buf.append(state)

    def _compute_trends(
        self,
        state: JunctionStatePacket,
    ) -> tuple[float, float]:
        """Compute smoothed arrival rate (veh/s) and queue velocity dQ/dt (m/s)."""
        buf = self.history[state.junction_id]
        if not buf:
            return state.inflow_rate_vps, 0.0

        recent = list(buf)[-10:]
        smoothed_inflow = sum(pkt.inflow_rate_vps for pkt in recent) / len(recent)
        # Weight current observation more heavily for responsive surge tracking.
        blended_inflow = 0.6 * state.inflow_rate_vps + 0.4 * smoothed_inflow

        if len(buf) < 2:
            return blended_inflow, 0.0

        dt_total = buf[-1].timestamp - buf[0].timestamp
        if dt_total <= 0.0:
            return blended_inflow, 0.0

        dq_dt = (buf[-1].queue_length_m - buf[0].queue_length_m) / dt_total
        dq_dt_clamped = max(-5.0, min(5.0, dq_dt))
        return blended_inflow, dq_dt_clamped

    def _compute_travel_delay(
        self,
        upstream_state: JunctionStatePacket,
        target_state: JunctionStatePacket,
    ) -> float:
        """Estimate platoon travel delay (tau) across the free link distance."""
        free_link_m = max(
            0.0, target_state.link_length_m - target_state.queue_length_m
        )
        if free_link_m <= 0.0:
            return 0.0

        discharge_ratio = min(
            1.5,
            upstream_state.outflow_rate_vps / self.config.saturation_discharge_vps,
        )
        effective_speed_mps = max(
            _MIN_TRAVEL_SPEED_MPS,
            upstream_state.avg_speed_mps * (0.9 + 0.1 * discharge_ratio),
        )
        return free_link_m / effective_speed_mps

    def _compute_expected_discharge_volume(
        self,
        state: JunctionStatePacket,
        horizon_s: int,
    ) -> float:
        """Estimate arterial discharge volume over horizon_s based on active_phase."""
        phase = state.active_phase
        sat_rate = self.config.saturation_discharge_vps

        if phase == SignalPhase.EW_GREEN:
            # Active arterial green discharges immediately across most of the horizon.
            effective_green_s = min(
                float(horizon_s),
                max(20.0, 35.0 - min(15.0, state.phase_elapsed_s)),
            )
            return sat_rate * effective_green_s

        if phase == SignalPhase.ALL_RED_TO_EW:
            clearance_wait = max(0.0, 2.0 - state.phase_elapsed_s)
            effective_green_s = min(
                22.0, max(0.0, float(horizon_s) - clearance_wait)
            )
            return sat_rate * effective_green_s

        if phase == SignalPhase.NS_YELLOW:
            clearance_wait = max(0.0, 3.0 - state.phase_elapsed_s) + 2.0
            effective_green_s = min(
                20.0, max(0.0, float(horizon_s) - clearance_wait)
            )
            return sat_rate * effective_green_s

        if phase == SignalPhase.NS_GREEN and state.phase_elapsed_s >= 20.0:
            # Approaching end of opposing green: partial late discharge window.
            wait_to_green = max(0.0, 25.0 - state.phase_elapsed_s) + 5.0
            effective_green_s = min(
                15.0, max(0.0, float(horizon_s) - wait_to_green)
            )
            return sat_rate * effective_green_s

        # Red / transitioning away from arterial green: zero expected discharge.
        return 0.0

    def _estimate_shockwave_delay(self, state: JunctionStatePacket) -> float:
        """Estimate queue-clearance shockwave delay (seconds) ahead of an EV."""
        if state.queue_length_m <= 0.0:
            return 0.0

        effective_queue_m = state.queue_length_m
        if state.ev_detected and state.ev_distance_m is not None:
            effective_queue_m = min(state.queue_length_m, state.ev_distance_m)

        queued_pcus = effective_queue_m / self.config.effective_pcu_spacing_m
        discharge_cap = self.config.saturation_discharge_vps * self.config.effective_lanes
        base_clearance_s = queued_pcus / max(0.2, discharge_cap)
        phase_factor = 0.25 if state.active_phase == SignalPhase.EW_GREEN else 0.5
        return round(base_clearance_s * phase_factor, 2)

    def _estimate_ev_eta(
        self,
        junction_id: JunctionID,
        corridor_states: dict[JunctionID, JunctionStatePacket],
    ) -> float | None:
        """Compute local or upstream-propagated EV ETA with shockwave delay."""
        state = corridor_states[junction_id]
        if state.ev_detected:
            if state.ev_eta_s is not None:
                base_eta = state.ev_eta_s
            elif state.ev_distance_m is not None:
                speed = max(_MIN_EV_SPEED_MPS, state.avg_speed_mps)
                base_eta = state.ev_distance_m / speed
            else:
                base_eta = 10.0
            return round(base_eta + self._estimate_shockwave_delay(state), 2)

        # Walk upstream chain to propagate EV ETA through intermediate links.
        upstream_chain: list[JunctionID] = []
        cursor = self._upstream_map.get(junction_id)
        visited: set[JunctionID] = {junction_id}
        while cursor is not None and cursor not in visited:
            visited.add(cursor)
            upstream_chain.append(cursor)
            if (
                cursor in corridor_states
                and corridor_states[cursor].ev_detected
            ):
                break
            cursor = self._upstream_map.get(cursor)
        else:
            return None

        source_id = upstream_chain[-1]
        if source_id not in corridor_states or not corridor_states[source_id].ev_detected:
            return None

        source_state = corridor_states[source_id]
        eta = self._estimate_ev_eta(source_id, corridor_states)
        if eta is None:
            return None

        # Traverse downstream from source_id -> ... -> junction_id.
        downstream_hops = list(reversed(upstream_chain[:-1])) + [junction_id]
        prev_state = source_state
        for hop_id in downstream_hops:
            hop_state = corridor_states.get(hop_id)
            if hop_state is None:
                return None
            ev_speed = max(
                _MIN_EV_SPEED_MPS,
                min(_MAX_EV_SPEED_MPS, max(prev_state.avg_speed_mps, _DEFAULT_EV_SPEED_MPS)),
            )
            link_travel_s = hop_state.link_length_m / ev_speed
            eta += link_travel_s + self._estimate_shockwave_delay(hop_state)
            prev_state = hop_state

        return round(eta, 2)

    def update_calibration(
        self,
        actual_states: dict[JunctionID, JunctionStatePacket],
    ) -> dict[JunctionID, float]:
        """Feed observed junction states back to the online residual calibrator."""
        return self.calibration.update_calibration(actual_states)

    def predict_junction(
        self,
        junction_id: JunctionID,
        corridor_states: dict[JunctionID, JunctionStatePacket],
        horizon_s: int | None = None,
    ) -> SpillbackForecast:
        """Forecast queue length, occupancy, spillback risk, and EV ETA for a junction."""
        if junction_id not in corridor_states:
            raise KeyError(f"Missing state packet for junction {junction_id}")

        state = corridor_states[junction_id]
        self._record_state(state)

        effective_horizon = (
            self.config.default_horizon_s
            if horizon_s is None
            else min(60, max(30, horizon_s))
        )

        smoothed_inflow, dq_dt = self._compute_trends(state)
        upstream_id = self._upstream_map.get(junction_id)

        if upstream_id is not None and upstream_id in corridor_states:
            upstream_state = corridor_states[upstream_id]
            self._record_state(upstream_state)
            travel_delay_s = self._compute_travel_delay(upstream_state, state)
            arrival_window_s = max(0.0, float(effective_horizon) - travel_delay_s)
            upstream_platoon_veh = upstream_state.outflow_rate_vps * arrival_window_s
            local_turning_veh = (
                smoothed_inflow * _TURNING_INFLOW_SHARE * float(effective_horizon)
            )
            incoming_volume_veh = upstream_platoon_veh + local_turning_veh
        else:
            incoming_volume_veh = smoothed_inflow * float(effective_horizon)

        discharge_volume_veh = self._compute_expected_discharge_volume(
            state, effective_horizon
        )
        net_vehicle_delta = incoming_volume_veh - discharge_volume_veh

        pcu_factor = _mean_pcu_per_vehicle(state.vehicle_mix)
        physics_queue_delta_m = (
            net_vehicle_delta * pcu_factor * self.config.effective_pcu_spacing_m
        ) / self.config.effective_lanes
        velocity_trend_m = 0.15 * dq_dt * float(effective_horizon)
        calibration_bias_m = self.calibration.get_bias(junction_id)

        raw_predicted_queue_m = (
            state.queue_length_m
            + physics_queue_delta_m
            + velocity_trend_m
            + calibration_bias_m
        )
        predicted_queue_length_m = round(
            min(1.5 * state.link_length_m, max(0.0, raw_predicted_queue_m)), 2
        )

        spillback_risk_index = round(
            min(1.5, max(0.0, predicted_queue_length_m / state.link_length_m)), 4
        )
        predicted_occupancy_ratio = round(
            min(1.0, max(0.0, predicted_queue_length_m / state.link_length_m)), 4
        )
        spillback_imminent = spillback_risk_index >= self.config.spillback_threshold
        predicted_ev_eta_s = self._estimate_ev_eta(junction_id, corridor_states)

        self.calibration.record_prediction(
            junction_id=junction_id,
            target_timestamp_s=state.timestamp + float(effective_horizon),
            predicted_queue_length_m=predicted_queue_length_m,
        )

        return SpillbackForecast(
            junction_id=junction_id,
            timestamp=state.timestamp,
            horizon_s=effective_horizon,
            predicted_occupancy_ratio=predicted_occupancy_ratio,
            predicted_queue_length_m=predicted_queue_length_m,
            spillback_risk_index=spillback_risk_index,
            spillback_imminent=spillback_imminent,
            predicted_ev_eta_s=predicted_ev_eta_s,
        )

    def predict_corridor(
        self,
        corridor_states: dict[JunctionID, JunctionStatePacket],
        horizon_s: int | None = None,
    ) -> dict[JunctionID, SpillbackForecast]:
        """Generate synchronized SpillbackForecast objects for J_A, J_B, and J_C."""
        for state in corridor_states.values():
            self._record_state(state)

        return {
            junction_id: self.predict_junction(
                junction_id=junction_id,
                corridor_states=corridor_states,
                horizon_s=horizon_s,
            )
            for junction_id in JunctionID
        }
