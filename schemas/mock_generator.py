"""Deterministic mock corridor telemetry generator for AegisFlow testing.

Simulates 120 seconds of synchronized JunctionStatePacket frames across
J_A, J_B, and J_C, featuring an ambulance entering J_A at t=20s while
congestion builds toward spillback at J_B.
"""

import random
from collections.abc import Iterator

from schemas.contracts import (
    JunctionID,
    JunctionStatePacket,
    SignalPhase,
    VehicleMix,
)

_PHASE_SCHEDULE: tuple[tuple[SignalPhase, int], ...] = (
    (SignalPhase.NS_GREEN, 25),
    (SignalPhase.NS_YELLOW, 3),
    (SignalPhase.ALL_RED_TO_EW, 2),
    (SignalPhase.EW_GREEN, 20),
    (SignalPhase.EW_YELLOW, 3),
    (SignalPhase.ALL_RED_TO_NS, 2),
)
_CYCLE_DURATION_S: int = sum(duration for _, duration in _PHASE_SCHEDULE)
_PHASE_OFFSETS_S: dict[JunctionID, int] = {
    JunctionID.J_A: 0,
    JunctionID.J_B: 15,
    JunctionID.J_C: 30,
}


def _resolve_phase(junction_id: JunctionID, tick_s: int) -> tuple[SignalPhase, float]:
    """Return the active signal phase and elapsed seconds at a given tick."""
    cycle_pos = (tick_s + _PHASE_OFFSETS_S[junction_id]) % _CYCLE_DURATION_S
    elapsed = 0
    for phase, duration in _PHASE_SCHEDULE:
        if cycle_pos < elapsed + duration:
            return phase, float(cycle_pos - elapsed)
        elapsed += duration
    return SignalPhase.NS_GREEN, 0.0


def _compute_pcu_density(mix: VehicleMix, link_length_m: float) -> float:
    """Compute Indian PCU-weighted linear density (PCU per 100m)."""
    total_pcu = (
        0.5 * mix.motorcycles
        + 0.8 * mix.auto_rickshaws
        + 1.0 * mix.cars
        + 2.5 * mix.buses_trucks
        + 1.5 * mix.emergency_vehicles
    )
    return round((total_pcu / link_length_m) * 100.0, 3)


class MockCorridorGenerator:
    """Deterministic generator yielding 120s of synchronized corridor frames."""

    def __init__(
        self,
        seed: int = 42,
        duration_s: int = 120,
        link_length_m: float = 300.0,
    ) -> None:
        """Initialize the corridor generator with a fixed PRNG seed."""
        self.seed = seed
        self.duration_s = duration_s
        self.link_length_m = link_length_m

    def _build_ev_state(
        self,
        junction_id: JunctionID,
        tick_s: int,
    ) -> tuple[bool, float, float | None, float | None]:
        """Compute deterministic emergency vehicle presence and kinematics."""
        # Ambulance enters J_A approach at t=20s, clears J_A by t=38s,
        # traverses J_B from t=42s..62s, and reaches J_C from t=66s..84s.
        windows: dict[JunctionID, tuple[int, int, float]] = {
            JunctionID.J_A: (20, 38, 14.0),
            JunctionID.J_B: (42, 62, 11.0),
            JunctionID.J_C: (66, 84, 13.5),
        }
        start_t, end_t, speed_mps = windows[junction_id]
        if start_t <= tick_s <= end_t:
            remaining_s = float(end_t - tick_s)
            distance_m = round(remaining_s * speed_mps, 2)
            confidence = round(min(0.99, 0.86 + 0.007 * (tick_s - start_t)), 3)
            return True, confidence, remaining_s, distance_m
        return False, 0.0, None, None

    def _build_packet(
        self,
        junction_id: JunctionID,
        tick_s: int,
        rng: random.Random,
    ) -> JunctionStatePacket:
        """Construct a single JunctionStatePacket for a junction and tick."""
        phase, phase_elapsed = _resolve_phase(junction_id, tick_s)
        ev_detected, ev_conf, ev_eta_s, ev_dist_m = self._build_ev_state(
            junction_id,
            tick_s,
        )

        # J_B accumulates heavy congestion toward spillback (~0.92 occupancy).
        if junction_id == JunctionID.J_B:
            progress = min(1.0, tick_s / 95.0)
            base_occ = 0.34 + 0.58 * progress
        elif junction_id == JunctionID.J_A:
            base_occ = 0.28 + 0.16 * min(1.0, tick_s / 60.0)
        else:
            base_occ = 0.25 + 0.22 * min(1.0, tick_s / 80.0)

        jitter = rng.uniform(-0.02, 0.02)
        occupancy = round(max(0.05, min(0.98, base_occ + jitter)), 4)
        queue_length_m = round(min(self.link_length_m, occupancy * self.link_length_m), 2)

        scale = occupancy * 2.2
        mix = VehicleMix(
            motorcycles=max(1, round(18 * scale + rng.randint(0, 3))),
            auto_rickshaws=max(0, round(9 * scale + rng.randint(0, 2))),
            cars=max(1, round(12 * scale + rng.randint(0, 2))),
            buses_trucks=max(0, round(3 * scale + rng.randint(0, 1))),
            emergency_vehicles=1 if ev_detected else 0,
        )

        avg_speed_mps = round(max(1.2, 14.5 * (1.0 - 0.85 * occupancy)), 2)
        inflow_rate_vps = round(
            (0.95 if junction_id == JunctionID.J_B else 0.55) + rng.uniform(0.0, 0.15),
            3,
        )
        is_green = phase in (SignalPhase.NS_GREEN, SignalPhase.EW_GREEN)
        discharge_cap = 0.65 if junction_id == JunctionID.J_B else 0.85
        outflow_rate_vps = round(
            (discharge_cap if is_green else 0.05) + rng.uniform(0.0, 0.05),
            3,
        )

        return JunctionStatePacket(
            junction_id=junction_id,
            timestamp=float(tick_s),
            source="mock",
            active_phase=phase,
            phase_elapsed_s=phase_elapsed,
            spatial_occupancy_ratio=occupancy,
            pcu_density=_compute_pcu_density(mix, self.link_length_m),
            queue_length_m=queue_length_m,
            link_length_m=self.link_length_m,
            avg_speed_mps=avg_speed_mps,
            inflow_rate_vps=inflow_rate_vps,
            outflow_rate_vps=outflow_rate_vps,
            vehicle_mix=mix,
            ev_detected=ev_detected,
            ev_confidence=ev_conf,
            ev_eta_s=ev_eta_s,
            ev_distance_m=ev_dist_m,
        )

    def generate(self) -> Iterator[dict[JunctionID, JunctionStatePacket]]:
        """Yield synchronized per-tick packets keyed by JunctionID."""
        rng = random.Random(self.seed)
        for tick_s in range(self.duration_s):
            yield {
                junction_id: self._build_packet(junction_id, tick_s, rng)
                for junction_id in JunctionID
            }

    def __iter__(self) -> Iterator[dict[JunctionID, JunctionStatePacket]]:
        """Iterate over synchronized corridor frames."""
        return self.generate()


if __name__ == "__main__":
    generator = MockCorridorGenerator(seed=42)
    frames = list(generator)
    sample_frame = frames[20]
    for junction_id in JunctionID:
        print(sample_frame[junction_id].model_dump_json(indent=2))
