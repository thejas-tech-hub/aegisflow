"""Unit tests for AegisFlow inter-module contracts and mock generator."""

import pytest
from pydantic import ValidationError

from schemas import (
    ControlActionType,
    JunctionID,
    JunctionStatePacket,
    ProposedControlAction,
    ShieldDecision,
    SignalPhase,
    SpillbackForecast,
    VehicleMix,
    VerifiedSignalCommand,
)
from schemas.mock_generator import MockCorridorGenerator


def test_contracts_valid_instantiation_and_json_roundtrip() -> None:
    """Verify valid creation and JSON round-trip for all 4 contracts."""
    state = JunctionStatePacket(
        junction_id=JunctionID.J_A,
        timestamp=20.0,
        source="cctv",
        active_phase=SignalPhase.NS_GREEN,
        phase_elapsed_s=12.0,
        spatial_occupancy_ratio=0.45,
        pcu_density=14.2,
        queue_length_m=120.0,
        link_length_m=300.0,
        avg_speed_mps=8.5,
        inflow_rate_vps=0.6,
        outflow_rate_vps=0.8,
        vehicle_mix=VehicleMix(
            motorcycles=12,
            auto_rickshaws=5,
            cars=8,
            buses_trucks=2,
            emergency_vehicles=1,
        ),
        ev_detected=True,
        ev_confidence=0.94,
        ev_eta_s=14.0,
        ev_distance_m=180.0,
    )
    forecast = SpillbackForecast(
        junction_id=JunctionID.J_B,
        timestamp=20.0,
        horizon_s=45,
        predicted_occupancy_ratio=0.91,
        predicted_queue_length_m=273.0,
        spillback_risk_index=1.18,
        spillback_imminent=True,
        predicted_ev_eta_s=38.0,
    )
    proposal = ProposedControlAction(
        junction_id=JunctionID.J_A,
        timestamp=20.0,
        target_phase=SignalPhase.NS_GREEN,
        action_type=ControlActionType.GREEN_EXTENSION,
        requested_duration_s=15.0,
        reason="EV approaching J_A while J_B risk elevated.",
        priority_score=0.92,
    )
    command = VerifiedSignalCommand(
        junction_id=JunctionID.J_A,
        timestamp=20.0,
        approved_phase=SignalPhase.NS_GREEN,
        approved_duration_s=15.0,
        shield_decision=ShieldDecision.APPROVED,
        original_action_type=ControlActionType.GREEN_EXTENSION,
        violated_invariants=[],
        audit_message="All municipal signal invariants satisfied.",
    )

    assert JunctionStatePacket.model_validate_json(state.model_dump_json()) == state
    assert SpillbackForecast.model_validate_json(forecast.model_dump_json()) == forecast
    assert (
        ProposedControlAction.model_validate_json(proposal.model_dump_json())
        == proposal
    )
    assert (
        VerifiedSignalCommand.model_validate_json(command.model_dump_json()) == command
    )


def test_junction_state_packet_validation_failures() -> None:
    """Verify ValidationError on out-of-range occupancy, queue, and junction_id."""
    base_kwargs = {
        "junction_id": JunctionID.J_A,
        "timestamp": 10.0,
        "source": "sumo",
        "active_phase": SignalPhase.EW_GREEN,
        "phase_elapsed_s": 5.0,
        "spatial_occupancy_ratio": 0.5,
        "pcu_density": 10.0,
        "queue_length_m": 80.0,
        "avg_speed_mps": 7.0,
        "inflow_rate_vps": 0.5,
        "outflow_rate_vps": 0.5,
        "vehicle_mix": VehicleMix(cars=4),
        "ev_detected": False,
        "ev_confidence": 0.0,
    }

    with pytest.raises(ValidationError):
        JunctionStatePacket(**{**base_kwargs, "spatial_occupancy_ratio": 1.05})

    with pytest.raises(ValidationError):
        JunctionStatePacket(**{**base_kwargs, "queue_length_m": -5.0})

    with pytest.raises(ValidationError):
        JunctionStatePacket(**{**base_kwargs, "junction_id": "J_Z"})


def test_mock_corridor_generator_120_ticks_and_ev_at_ja() -> None:
    """Verify 120 synchronized ticks, determinism, EV at J_A, and J_B buildup."""
    gen_a = MockCorridorGenerator(seed=42)
    gen_b = MockCorridorGenerator(seed=42)

    frames_a = list(gen_a)
    frames_b = list(gen_b)

    assert len(frames_a) == 120
    assert frames_a == frames_b

    for tick, frame in enumerate(frames_a):
        assert set(frame.keys()) == {JunctionID.J_A, JunctionID.J_B, JunctionID.J_C}
        for packet in frame.values():
            assert isinstance(packet, JunctionStatePacket)
            assert packet.timestamp == float(tick)

    assert frames_a[20][JunctionID.J_A].ev_detected is True
    assert frames_a[20][JunctionID.J_A].vehicle_mix.emergency_vehicles == 1
    assert frames_a[10][JunctionID.J_A].ev_detected is False
    assert (
        frames_a[-1][JunctionID.J_B].spatial_occupancy_ratio
        > frames_a[0][JunctionID.J_B].spatial_occupancy_ratio
    )
