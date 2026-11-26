"""Deterministic 1-second-step 1D corridor physics simulator for A/B benchmarking.

Models J_A (x=0m), J_B (x=300m), and J_C (x=600m) across a 900m eastbound
arterial corridor with realistic Indian heterogeneous traffic queues,
upstream-to-downstream discharge coupling, and physical ambulance spillback
blocking physics.
"""

import random
from dataclasses import dataclass
from typing import Literal

from schemas.contracts import (
    JunctionID,
    JunctionStatePacket,
    SignalPhase,
    VehicleMix,
    VerifiedSignalCommand,
)

ScenarioPreset = Literal["peak_spillback", "moderate_mixed", "severe_gridlock"]

_JUNCTION_X_M: dict[JunctionID, float] = {
    JunctionID.J_A: 0.0,
    JunctionID.J_B: 300.0,
    JunctionID.J_C: 600.0,
}
_LINK_LENGTH_M = 300.0
_EV_START_X_M = -180.0
_EV_EXIT_X_M = 750.0
_EV_CRUISE_SPEED_MPS = 14.0
_DETECTION_RANGE_M = 300.0
_EFFECTIVE_PCU_SPACING_M = 6.5
_EFFECTIVE_LANES = 2.0
_MEAN_PCU_FACTOR = 1.1
_SPILLBACK_OCCUPANCY_THRESHOLD = 0.78


@dataclass
class _JunctionRuntime:
    """Mutable per-junction physical state inside CorridorPhysicsSim."""

    active_phase: SignalPhase
    phase_elapsed_s: float
    queue_length_m: float
    base_inflow_vps: float
    saturation_discharge_vps: float
    inflow_rate_vps: float
    outflow_rate_vps: float
    avg_speed_mps: float
    peak_queue_m: float
    spillback_ticks: int = 0


def _scenario_defaults(
    scenario: ScenarioPreset,
) -> dict[JunctionID, tuple[SignalPhase, float, float, float, float]]:
    """Return initial (phase, elapsed_s, queue_m, base_inflow, sat_discharge)."""
    if scenario == "moderate_mixed":
        return {
            JunctionID.J_A: (SignalPhase.NS_GREEN, 10.0, 40.0, 0.42, 2.2),
            JunctionID.J_B: (SignalPhase.NS_GREEN, 12.0, 95.0, 0.35, 2.2),
            JunctionID.J_C: (SignalPhase.NS_GREEN, 14.0, 55.0, 0.32, 2.2),
        }
    if scenario == "severe_gridlock":
        return {
            JunctionID.J_A: (SignalPhase.NS_GREEN, 8.0, 90.0, 0.65, 2.3),
            JunctionID.J_B: (SignalPhase.NS_GREEN, 8.0, 215.0, 0.55, 2.35),
            JunctionID.J_C: (SignalPhase.NS_GREEN, 10.0, 140.0, 0.48, 2.3),
        }
    # Default: "peak_spillback"
    return {
        JunctionID.J_A: (SignalPhase.NS_GREEN, 10.0, 45.0, 0.52, 2.4),
        JunctionID.J_B: (SignalPhase.NS_GREEN, 10.0, 190.0, 0.48, 2.45),
        JunctionID.J_C: (SignalPhase.NS_GREEN, 12.0, 70.0, 0.38, 2.4),
    }


class CorridorPhysicsSim:
    """Deterministic 1s-tick physical corridor simulator for fair A/B comparison."""

    def __init__(
        self,
        scenario: ScenarioPreset = "peak_spillback",
        seed: int = 42,
    ) -> None:
        """Initialize corridor junctions, deterministic PRNG, and EV position."""
        self.scenario: ScenarioPreset = scenario
        self.seed = seed
        self._rng = random.Random(seed)
        self.tick: int = 0

        self.ev_position_m: float = _EV_START_X_M
        self.ev_speed_mps: float = _EV_CRUISE_SPEED_MPS
        self.ev_stopped_time_s: float = 0.0
        self.ev_trapped_in_spillback: bool = False
        self.ev_completed: bool = False
        self.ev_travel_time_s: float | None = None

        defaults = _scenario_defaults(scenario)
        self._junctions: dict[JunctionID, _JunctionRuntime] = {}
        for jid, (phase, elapsed, queue_m, inflow, sat) in defaults.items():
            occ = min(1.0, queue_m / _LINK_LENGTH_M)
            self._junctions[jid] = _JunctionRuntime(
                active_phase=phase,
                phase_elapsed_s=elapsed,
                queue_length_m=queue_m,
                base_inflow_vps=inflow,
                saturation_discharge_vps=sat,
                inflow_rate_vps=inflow,
                outflow_rate_vps=0.05,
                avg_speed_mps=round(max(1.5, 14.0 * (1.0 - 0.8 * occ)), 2),
                peak_queue_m=queue_m,
                spillback_ticks=1 if occ >= _SPILLBACK_OCCUPANCY_THRESHOLD else 0,
            )

    def _ev_junction_telemetry(
        self, junction_id: JunctionID
    ) -> tuple[bool, float, float | None, float | None]:
        """Compute EV detection, confidence, ETA, and distance for one junction."""
        if self.ev_completed:
            return False, 0.0, None, None

        jx = _JUNCTION_X_M[junction_id]
        approach_start_x = jx - _DETECTION_RANGE_M
        if approach_start_x <= self.ev_position_m <= jx:
            dist_m = round(max(0.0, jx - self.ev_position_m), 2)
            effective_speed = max(4.0, self.ev_speed_mps)
            eta_s = round(dist_m / effective_speed, 2)
            confidence = round(max(0.86, min(0.99, 0.99 - 0.0004 * dist_m)), 3)
            return True, confidence, eta_s, dist_m
        return False, 0.0, None, None

    def _build_vehicle_mix(
        self,
        occupancy: float,
        ev_detected: bool,
    ) -> VehicleMix:
        """Synthesize heterogeneous Indian traffic counts consistent with occupancy."""
        scale = max(0.2, occupancy * 2.2)
        if self.scenario == "severe_gridlock":
            scale *= 1.15
        return VehicleMix(
            motorcycles=max(1, round(16 * scale)),
            auto_rickshaws=max(0, round(8 * scale)),
            cars=max(1, round(10 * scale)),
            buses_trucks=max(0, round(3 * scale)),
            emergency_vehicles=1 if ev_detected else 0,
        )

    def _compute_pcu_density(self, mix: VehicleMix) -> float:
        """Compute Indian PCU-weighted density (PCU per 100m)."""
        total_pcu = (
            0.5 * mix.motorcycles
            + 0.8 * mix.auto_rickshaws
            + 1.0 * mix.cars
            + 2.5 * mix.buses_trucks
            + 1.5 * mix.emergency_vehicles
        )
        return round((total_pcu / _LINK_LENGTH_M) * 100.0, 3)

    def get_state_packets(self) -> dict[JunctionID, JunctionStatePacket]:
        """Emit synchronized JunctionStatePacket snapshots for J_A, J_B, and J_C."""
        packets: dict[JunctionID, JunctionStatePacket] = {}
        for jid in JunctionID:
            jr = self._junctions[jid]
            occ = round(min(1.0, max(0.0, jr.queue_length_m / _LINK_LENGTH_M)), 4)
            ev_det, ev_conf, ev_eta, ev_dist = self._ev_junction_telemetry(jid)
            mix = self._build_vehicle_mix(occ, ev_det)
            packets[jid] = JunctionStatePacket(
                junction_id=jid,
                timestamp=float(self.tick),
                source="sumo",
                active_phase=jr.active_phase,
                phase_elapsed_s=jr.phase_elapsed_s,
                spatial_occupancy_ratio=occ,
                pcu_density=self._compute_pcu_density(mix),
                queue_length_m=round(jr.queue_length_m, 2),
                link_length_m=_LINK_LENGTH_M,
                avg_speed_mps=jr.avg_speed_mps,
                inflow_rate_vps=round(jr.inflow_rate_vps, 3),
                outflow_rate_vps=round(jr.outflow_rate_vps, 3),
                vehicle_mix=mix,
                ev_detected=ev_det,
                ev_confidence=ev_conf,
                ev_eta_s=ev_eta,
                ev_distance_m=ev_dist,
            )
        return packets

    def _update_ambulance_kinematics(self) -> None:
        """Advance ambulance 1D coordinate or stall it inside blocking queues."""
        if self.ev_completed:
            self.ev_speed_mps = 0.0
            self.ev_trapped_in_spillback = False
            return

        target_jid: JunctionID | None = None
        for jid in (JunctionID.J_A, JunctionID.J_B, JunctionID.J_C):
            jx = _JUNCTION_X_M[jid]
            if self.ev_position_m <= jx:
                target_jid = jid
                break

        blocked = False
        if target_jid is not None:
            jr = self._junctions[target_jid]
            jx = _JUNCTION_X_M[target_jid]
            queue_tail_x = jx - jr.queue_length_m

            # Standing queue tail blocks EV, or red signal reached at stop line.
            if (jr.queue_length_m > 5.0 and self.ev_position_m >= queue_tail_x) or (
                jr.active_phase != SignalPhase.EW_GREEN
                and self.ev_position_m >= jx - 10.0
            ):
                blocked = True

        if blocked:
            self.ev_speed_mps = 0.0
            self.ev_trapped_in_spillback = True
            self.ev_stopped_time_s += 1.0
        else:
            self.ev_speed_mps = _EV_CRUISE_SPEED_MPS
            self.ev_trapped_in_spillback = False
            self.ev_position_m = round(
                min(_EV_EXIT_X_M, self.ev_position_m + _EV_CRUISE_SPEED_MPS), 2
            )
            if self.ev_position_m >= _EV_EXIT_X_M:
                self.ev_completed = True
                self.ev_travel_time_s = float(self.tick + 1)

    def apply_commands(
        self,
        commands: dict[JunctionID, VerifiedSignalCommand],
    ) -> None:
        """Apply Safety-Shield-verified signal commands and advance physics by 1s."""
        for jid, cmd in commands.items():
            jr = self._junctions[jid]
            if cmd.approved_phase != jr.active_phase:
                jr.active_phase = cmd.approved_phase
                jr.phase_elapsed_s = 0.0

        # Sample deterministic inflow noise in topological order.
        noise_by_jid = {
            jid: self._rng.uniform(-0.04, 0.04) for jid in JunctionID
        }

        prev_outflow = 0.0
        for idx, jid in enumerate((JunctionID.J_A, JunctionID.J_B, JunctionID.J_C)):
            jr = self._junctions[jid]
            if idx == 0:
                inflow = max(0.1, jr.base_inflow_vps + noise_by_jid[jid])
            else:
                # Downstream link receives upstream arterial discharge + local turns.
                inflow = max(
                    0.1,
                    0.55 * prev_outflow + jr.base_inflow_vps + noise_by_jid[jid],
                )

            if jr.active_phase == SignalPhase.EW_GREEN:
                if jr.queue_length_m > 4.0:
                    outflow = jr.saturation_discharge_vps
                else:
                    outflow = min(jr.saturation_discharge_vps, inflow)
            else:
                outflow = 0.05 if jr.queue_length_m > 0.0 else 0.0

            net_vps = inflow - outflow
            dq_m = (
                net_vps * _MEAN_PCU_FACTOR * _EFFECTIVE_PCU_SPACING_M
            ) / _EFFECTIVE_LANES

            jr.queue_length_m = round(
                min(_LINK_LENGTH_M, max(0.0, jr.queue_length_m + dq_m)), 2
            )
            jr.inflow_rate_vps = inflow
            jr.outflow_rate_vps = outflow
            occ = min(1.0, jr.queue_length_m / _LINK_LENGTH_M)
            jr.avg_speed_mps = round(max(1.5, 14.0 * (1.0 - 0.8 * occ)), 2)
            jr.peak_queue_m = max(jr.peak_queue_m, jr.queue_length_m)
            if occ >= _SPILLBACK_OCCUPANCY_THRESHOLD:
                jr.spillback_ticks += 1

            jr.phase_elapsed_s += 1.0
            prev_outflow = outflow

        self._update_ambulance_kinematics()
        self.tick += 1

    def get_kpis(self) -> dict[str, float | int | bool | None]:
        """Return current corridor performance KPIs for benchmark comparison."""
        peak_queue = max(jr.peak_queue_m for jr in self._junctions.values())
        spillback_ticks = sum(jr.spillback_ticks for jr in self._junctions.values())
        return {
            "ev_travel_time_s": self.ev_travel_time_s,
            "ev_stopped_time_s": round(self.ev_stopped_time_s, 2),
            "peak_queue_length_m": round(peak_queue, 2),
            "spillback_ticks": spillback_ticks,
            "ev_completed": self.ev_completed,
        }
