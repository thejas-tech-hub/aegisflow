"""Adversarial unit and integration tests for DeterministicSafetyShield."""

from safety_shield import DeterministicSafetyShield, SafetyConfig
from schemas.contracts import (
    ControlActionType,
    JunctionID,
    JunctionStatePacket,
    ProposedControlAction,
    ShieldDecision,
    SignalPhase,
    VehicleMix,
    VerifiedSignalCommand,
)
from schemas.mock_generator import MockCorridorGenerator


def _make_state(
    junction_id: JunctionID = JunctionID.J_A,
    timestamp: float = 15.0,
    active_phase: SignalPhase = SignalPhase.NS_GREEN,
    phase_elapsed_s: float = 15.0,
) -> JunctionStatePacket:
    """Create a valid JunctionStatePacket fixture for safety shield tests."""
    return JunctionStatePacket(
        junction_id=junction_id,
        timestamp=timestamp,
        source="sumo",
        active_phase=active_phase,
        phase_elapsed_s=phase_elapsed_s,
        spatial_occupancy_ratio=0.42,
        pcu_density=12.5,
        queue_length_m=95.0,
        link_length_m=300.0,
        avg_speed_mps=9.2,
        inflow_rate_vps=0.5,
        outflow_rate_vps=0.7,
        vehicle_mix=VehicleMix(motorcycles=10, cars=6, emergency_vehicles=1),
        ev_detected=True,
        ev_confidence=0.95,
        ev_eta_s=12.0,
        ev_distance_m=150.0,
    )


def _make_proposal(
    junction_id: JunctionID = JunctionID.J_A,
    timestamp: float = 15.0,
    target_phase: SignalPhase = SignalPhase.NS_GREEN,
    action_type: ControlActionType = ControlActionType.HOLD,
    requested_duration_s: float = 20.0,
) -> ProposedControlAction:
    """Create a ProposedControlAction fixture for safety shield tests."""
    return ProposedControlAction(
        junction_id=junction_id,
        timestamp=timestamp,
        target_phase=target_phase,
        action_type=action_type,
        requested_duration_s=requested_duration_s,
        reason="Test orchestrator proposal.",
        priority_score=0.85,
    )


def test_normal_green_hold_and_extension_approved() -> None:
    """Normal valid green hold & extension within bounds must be APPROVED."""
    shield = DeterministicSafetyShield()

    hold_cmd = shield.verify(
        _make_state(timestamp=12.0, phase_elapsed_s=12.0),
        _make_proposal(
            timestamp=12.0,
            action_type=ControlActionType.HOLD,
            requested_duration_s=20.0,
        ),
    )
    ext_cmd = shield.verify(
        _make_state(timestamp=18.0, phase_elapsed_s=18.0),
        _make_proposal(
            timestamp=18.0,
            action_type=ControlActionType.GREEN_EXTENSION,
            requested_duration_s=30.0,
        ),
    )

    assert hold_cmd.shield_decision == ShieldDecision.APPROVED
    assert hold_cmd.approved_phase == SignalPhase.NS_GREEN
    assert hold_cmd.approved_duration_s == 20.0
    assert hold_cmd.violated_invariants == []

    assert ext_cmd.shield_decision == ShieldDecision.APPROVED
    assert ext_cmd.approved_phase == SignalPhase.NS_GREEN
    assert ext_cmd.approved_duration_s == 30.0
    assert ext_cmd.violated_invariants == []
    assert shield.get_audit_summary() == {
        "APPROVED": 2,
        "CLIPPED": 0,
        "VETOED": 0,
    }


def test_adversarial_direct_jump_before_min_green_vetoed() -> None:
    """Adversarial NS_GREEN -> EW_GREEN at t=4s violates MIN_GREEN_LOCK + MUTEX."""
    shield = DeterministicSafetyShield()
    cmd = shield.verify(
        _make_state(
            timestamp=4.0,
            active_phase=SignalPhase.NS_GREEN,
            phase_elapsed_s=4.0,
        ),
        _make_proposal(
            timestamp=4.0,
            target_phase=SignalPhase.EW_GREEN,
            action_type=ControlActionType.RED_TRUNCATION,
            requested_duration_s=20.0,
        ),
    )

    assert cmd.shield_decision == ShieldDecision.VETOED
    assert cmd.approved_phase == SignalPhase.NS_GREEN
    assert "MIN_GREEN_LOCK" in cmd.violated_invariants
    assert "CONFLICT_MUTEX" in cmd.violated_invariants


def test_phase_switch_enforces_full_yellow_and_all_red_clearance() -> None:
    """Switch at t=12s enforces NS_YELLOW (3s) -> ALL_RED_TO_EW (2s) -> EW_GREEN."""
    shield = DeterministicSafetyShield()

    # t=12s: AI requests EW_GREEN directly -> clipped to NS_YELLOW (3s).
    cmd_start_yellow = shield.verify(
        _make_state(
            timestamp=12.0,
            active_phase=SignalPhase.NS_GREEN,
            phase_elapsed_s=12.0,
        ),
        _make_proposal(
            timestamp=12.0,
            target_phase=SignalPhase.EW_GREEN,
            action_type=ControlActionType.RED_TRUNCATION,
            requested_duration_s=25.0,
        ),
    )
    assert cmd_start_yellow.shield_decision == ShieldDecision.CLIPPED
    assert cmd_start_yellow.approved_phase == SignalPhase.NS_YELLOW
    assert cmd_start_yellow.approved_duration_s == 3.0
    assert "MANDATORY_CLEARANCE" in cmd_start_yellow.violated_invariants

    # t=13s (1s into NS_YELLOW): AI attempts to jump early to EW_GREEN -> VETOED.
    cmd_mid_yellow = shield.verify(
        _make_state(
            timestamp=13.0,
            active_phase=SignalPhase.NS_YELLOW,
            phase_elapsed_s=1.0,
        ),
        _make_proposal(
            timestamp=13.0,
            target_phase=SignalPhase.EW_GREEN,
            action_type=ControlActionType.RED_TRUNCATION,
            requested_duration_s=25.0,
        ),
    )
    assert cmd_mid_yellow.shield_decision == ShieldDecision.VETOED
    assert cmd_mid_yellow.approved_phase == SignalPhase.NS_YELLOW
    assert "MANDATORY_CLEARANCE" in cmd_mid_yellow.violated_invariants

    # t=15s (3s of NS_YELLOW elapsed): advances to ALL_RED_TO_EW (2s).
    cmd_to_all_red = shield.verify(
        _make_state(
            timestamp=15.0,
            active_phase=SignalPhase.NS_YELLOW,
            phase_elapsed_s=3.0,
        ),
        _make_proposal(
            timestamp=15.0,
            target_phase=SignalPhase.ALL_RED_TO_EW,
            action_type=ControlActionType.HOLD,
            requested_duration_s=2.0,
        ),
    )
    assert cmd_to_all_red.shield_decision == ShieldDecision.APPROVED
    assert cmd_to_all_red.approved_phase == SignalPhase.ALL_RED_TO_EW
    assert cmd_to_all_red.approved_duration_s == 2.0

    # t=16s (1s into ALL_RED_TO_EW): AI tries to interrupt all-red -> VETOED.
    cmd_mid_all_red = shield.verify(
        _make_state(
            timestamp=16.0,
            active_phase=SignalPhase.ALL_RED_TO_EW,
            phase_elapsed_s=1.0,
        ),
        _make_proposal(
            timestamp=16.0,
            target_phase=SignalPhase.EW_GREEN,
            action_type=ControlActionType.GREEN_EXTENSION,
            requested_duration_s=25.0,
        ),
    )
    assert cmd_mid_all_red.shield_decision == ShieldDecision.VETOED
    assert cmd_mid_all_red.approved_phase == SignalPhase.ALL_RED_TO_EW
    assert "MANDATORY_CLEARANCE" in cmd_mid_all_red.violated_invariants

    # t=17s (2s of ALL_RED_TO_EW elapsed): cleanly enters EW_GREEN.
    cmd_to_ew_green = shield.verify(
        _make_state(
            timestamp=17.0,
            active_phase=SignalPhase.ALL_RED_TO_EW,
            phase_elapsed_s=2.0,
        ),
        _make_proposal(
            timestamp=17.0,
            target_phase=SignalPhase.EW_GREEN,
            action_type=ControlActionType.GREEN_EXTENSION,
            requested_duration_s=25.0,
        ),
    )
    assert cmd_to_ew_green.shield_decision == ShieldDecision.APPROVED
    assert cmd_to_ew_green.approved_phase == SignalPhase.EW_GREEN
    assert cmd_to_ew_green.approved_duration_s == 25.0


def test_anti_starvation_overrides_continuous_green_extension() -> None:
    """Continuous GREEN_EXTENSION for 115s must trigger MAX_RED_STARVATION override."""
    shield = DeterministicSafetyShield(SafetyConfig(max_cross_street_red_s=110.0))

    last_cmd: VerifiedSignalCommand | None = None
    for t in range(116):
        state = _make_state(
            timestamp=float(t),
            active_phase=SignalPhase.NS_GREEN,
            phase_elapsed_s=float(t),
        )
        proposal = _make_proposal(
            timestamp=float(t),
            target_phase=SignalPhase.NS_GREEN,
            action_type=ControlActionType.GREEN_EXTENSION,
            requested_duration_s=20.0,
        )
        last_cmd = shield.verify(state, proposal)

    assert last_cmd is not None
    assert last_cmd.shield_decision == ShieldDecision.VETOED
    assert last_cmd.approved_phase == SignalPhase.NS_YELLOW
    assert last_cmd.approved_duration_s == 3.0
    assert "MAX_RED_STARVATION" in last_cmd.violated_invariants


def test_excessive_duration_request_clipped_to_max_green() -> None:
    """Excessive requested_duration_s=250.0 must be CLIPPED to 75.0s."""
    shield = DeterministicSafetyShield()
    cmd = shield.verify(
        _make_state(timestamp=15.0, phase_elapsed_s=15.0),
        _make_proposal(
            timestamp=15.0,
            target_phase=SignalPhase.NS_GREEN,
            action_type=ControlActionType.GREEN_EXTENSION,
            requested_duration_s=250.0,
        ),
    )

    assert cmd.shield_decision == ShieldDecision.CLIPPED
    assert cmd.approved_phase == SignalPhase.NS_GREEN
    assert cmd.approved_duration_s == 75.0
    assert "DURATION_BOUNDS" in cmd.violated_invariants


def test_mock_corridor_integration_smoke_test() -> None:
    """Feed 120s of MockCorridorGenerator frames into shield with zero errors."""
    shield = DeterministicSafetyShield()
    generator = MockCorridorGenerator(seed=42)

    total_commands = 0
    for frame in generator:
        for junction_id, packet in frame.items():
            action = (
                ControlActionType.GREEN_EXTENSION
                if packet.ev_detected
                else ControlActionType.HOLD
            )
            proposal = ProposedControlAction(
                junction_id=junction_id,
                timestamp=packet.timestamp,
                target_phase=packet.active_phase,
                action_type=action,
                requested_duration_s=15.0,
                reason="Mock smoke test action.",
                priority_score=0.9 if packet.ev_detected else 0.3,
            )
            cmd = shield.verify(packet, proposal)
            assert isinstance(cmd, VerifiedSignalCommand)
            assert cmd.junction_id == junction_id
            total_commands += 1

    assert total_commands == 360
    summary = shield.get_audit_summary()
    assert sum(summary.values()) == 360
    assert len(shield.audit_log) == 360
