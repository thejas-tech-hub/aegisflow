"""Unit and closed-loop integration tests for CorridorOrchestrator & AegisFlowController."""

from orchestrator import AegisFlowController, CorridorOrchestrator
from predictor import SpillbackPredictor
from schemas.contracts import (
    ControlActionType,
    JunctionID,
    JunctionStatePacket,
    ProposedControlAction,
    SignalPhase,
    SpillbackForecast,
    VehicleMix,
    VerifiedSignalCommand,
)
from schemas.mock_generator import MockCorridorGenerator


def _make_state(
    junction_id: JunctionID,
    timestamp: float = 20.0,
    active_phase: SignalPhase = SignalPhase.NS_GREEN,
    phase_elapsed_s: float = 15.0,
    queue_length_m: float = 100.0,
    link_length_m: float = 300.0,
    avg_speed_mps: float = 10.0,
    inflow_rate_vps: float = 0.5,
    outflow_rate_vps: float = 0.6,
    ev_detected: bool = False,
    ev_eta_s: float | None = None,
) -> JunctionStatePacket:
    """Create a valid JunctionStatePacket fixture for orchestrator tests."""
    occupancy = min(1.0, max(0.0, queue_length_m / link_length_m))
    return JunctionStatePacket(
        junction_id=junction_id,
        timestamp=timestamp,
        source="sumo",
        active_phase=active_phase,
        phase_elapsed_s=phase_elapsed_s,
        spatial_occupancy_ratio=occupancy,
        pcu_density=12.0,
        queue_length_m=queue_length_m,
        link_length_m=link_length_m,
        avg_speed_mps=avg_speed_mps,
        inflow_rate_vps=inflow_rate_vps,
        outflow_rate_vps=outflow_rate_vps,
        vehicle_mix=VehicleMix(
            motorcycles=10,
            auto_rickshaws=4,
            cars=6,
            buses_trucks=2,
            emergency_vehicles=1 if ev_detected else 0,
        ),
        ev_detected=ev_detected,
        ev_confidence=0.95 if ev_detected else 0.0,
        ev_eta_s=ev_eta_s,
        ev_distance_m=(ev_eta_s * 12.0) if ev_eta_s is not None else None,
    )


def test_proactive_flush_at_jb_when_ev_detected_at_ja() -> None:
    """EV at J_A with downstream queue at J_B (NS_GREEN) triggers RED_TRUNCATION."""
    predictor = SpillbackPredictor()
    orchestrator = CorridorOrchestrator()

    states = {
        JunctionID.J_A: _make_state(
            JunctionID.J_A,
            active_phase=SignalPhase.EW_GREEN,
            queue_length_m=45.0,
            ev_detected=True,
            ev_eta_s=10.0,
        ),
        JunctionID.J_B: _make_state(
            JunctionID.J_B,
            active_phase=SignalPhase.NS_GREEN,
            queue_length_m=130.0,
            ev_detected=False,
        ),
        JunctionID.J_C: _make_state(
            JunctionID.J_C,
            active_phase=SignalPhase.NS_GREEN,
            queue_length_m=60.0,
            ev_detected=False,
        ),
    }

    forecasts = predictor.predict_corridor(states)
    proposals = orchestrator.decide_corridor(states, forecasts)

    jb_proposal = proposals[JunctionID.J_B]
    assert jb_proposal.action_type == ControlActionType.RED_TRUNCATION
    assert jb_proposal.target_phase == SignalPhase.EW_GREEN
    assert jb_proposal.priority_score >= 0.85


def test_green_extension_when_ev_within_8s_on_ew_green() -> None:
    """EV within 8s of J_B while EW_GREEN is active proposes GREEN_EXTENSION."""
    orchestrator = CorridorOrchestrator()

    states = {
        JunctionID.J_A: _make_state(JunctionID.J_A, queue_length_m=40.0),
        JunctionID.J_B: _make_state(
            JunctionID.J_B,
            active_phase=SignalPhase.EW_GREEN,
            queue_length_m=90.0,
            ev_detected=True,
            ev_eta_s=8.0,
        ),
        JunctionID.J_C: _make_state(JunctionID.J_C, queue_length_m=50.0),
    }
    forecasts = {
        JunctionID.J_A: SpillbackForecast(
            junction_id=JunctionID.J_A,
            timestamp=20.0,
            horizon_s=45,
            predicted_occupancy_ratio=0.20,
            predicted_queue_length_m=60.0,
            spillback_risk_index=0.20,
            spillback_imminent=False,
            predicted_ev_eta_s=None,
        ),
        JunctionID.J_B: SpillbackForecast(
            junction_id=JunctionID.J_B,
            timestamp=20.0,
            horizon_s=45,
            predicted_occupancy_ratio=0.32,
            predicted_queue_length_m=96.0,
            spillback_risk_index=0.32,
            spillback_imminent=False,
            predicted_ev_eta_s=10.0,
        ),
        JunctionID.J_C: SpillbackForecast(
            junction_id=JunctionID.J_C,
            timestamp=20.0,
            horizon_s=45,
            predicted_occupancy_ratio=0.22,
            predicted_queue_length_m=66.0,
            spillback_risk_index=0.22,
            spillback_imminent=False,
            predicted_ev_eta_s=38.0,
        ),
    }

    proposals = orchestrator.decide_corridor(states, forecasts)
    jb_proposal = proposals[JunctionID.J_B]

    assert jb_proposal.action_type == ControlActionType.GREEN_EXTENSION
    assert jb_proposal.target_phase == SignalPhase.EW_GREEN
    assert jb_proposal.priority_score >= 0.90


def test_upstream_metering_when_ev_passed_ja_and_jb_spillback_imminent() -> None:
    """EV passed J_A while J_B has spillback_imminent=True -> J_A proposes UPSTREAM_METERING."""
    orchestrator = CorridorOrchestrator()

    states = {
        JunctionID.J_A: _make_state(
            JunctionID.J_A,
            active_phase=SignalPhase.EW_GREEN,
            queue_length_m=60.0,
            ev_detected=False,
        ),
        JunctionID.J_B: _make_state(
            JunctionID.J_B,
            active_phase=SignalPhase.NS_GREEN,
            queue_length_m=240.0,
            ev_detected=True,
            ev_eta_s=12.0,
        ),
        JunctionID.J_C: _make_state(JunctionID.J_C, queue_length_m=75.0),
    }
    forecasts = {
        JunctionID.J_A: SpillbackForecast(
            junction_id=JunctionID.J_A,
            timestamp=45.0,
            horizon_s=45,
            predicted_occupancy_ratio=0.25,
            predicted_queue_length_m=75.0,
            spillback_risk_index=0.25,
            spillback_imminent=False,
            predicted_ev_eta_s=None,
        ),
        JunctionID.J_B: SpillbackForecast(
            junction_id=JunctionID.J_B,
            timestamp=45.0,
            horizon_s=45,
            predicted_occupancy_ratio=0.92,
            predicted_queue_length_m=276.0,
            spillback_risk_index=0.92,
            spillback_imminent=True,
            predicted_ev_eta_s=16.0,
        ),
        JunctionID.J_C: SpillbackForecast(
            junction_id=JunctionID.J_C,
            timestamp=45.0,
            horizon_s=45,
            predicted_occupancy_ratio=0.35,
            predicted_queue_length_m=105.0,
            spillback_risk_index=0.35,
            spillback_imminent=False,
            predicted_ev_eta_s=44.0,
        ),
    }

    proposals = orchestrator.decide_corridor(states, forecasts)
    ja_proposal = proposals[JunctionID.J_A]

    assert ja_proposal.action_type == ControlActionType.UPSTREAM_METERING
    assert ja_proposal.target_phase == SignalPhase.NS_GREEN


def test_post_ev_recovery_triggered_after_ambulance_exits() -> None:
    """When EV clears a junction on EW_GREEN, orchestrator proposes RECOVERY to NS_GREEN."""
    orchestrator = CorridorOrchestrator()

    states_ev = {
        jid: _make_state(
            jid,
            timestamp=25.0,
            active_phase=SignalPhase.EW_GREEN,
            queue_length_m=50.0,
            ev_detected=(jid == JunctionID.J_A),
            ev_eta_s=6.0 if jid == JunctionID.J_A else None,
        )
        for jid in JunctionID
    }
    forecasts_ev = {
        jid: SpillbackForecast(
            junction_id=jid,
            timestamp=25.0,
            horizon_s=45,
            predicted_occupancy_ratio=0.20,
            predicted_queue_length_m=60.0,
            spillback_risk_index=0.20,
            spillback_imminent=False,
            predicted_ev_eta_s=7.0 if jid == JunctionID.J_A else None,
        )
        for jid in JunctionID
    }
    orchestrator.decide_corridor(states_ev, forecasts_ev)

    states_cleared = {
        jid: _make_state(
            jid,
            timestamp=32.0,
            active_phase=SignalPhase.EW_GREEN,
            queue_length_m=40.0,
            ev_detected=False,
        )
        for jid in JunctionID
    }
    forecasts_cleared = {
        jid: SpillbackForecast(
            junction_id=jid,
            timestamp=32.0,
            horizon_s=45,
            predicted_occupancy_ratio=0.18,
            predicted_queue_length_m=54.0,
            spillback_risk_index=0.18,
            spillback_imminent=False,
            predicted_ev_eta_s=None,
        )
        for jid in JunctionID
    }
    proposals = orchestrator.decide_corridor(states_cleared, forecasts_cleared)

    assert proposals[JunctionID.J_A].action_type == ControlActionType.RECOVERY
    assert proposals[JunctionID.J_A].target_phase == SignalPhase.NS_GREEN


def test_end_to_end_closed_loop_120_ticks() -> None:
    """Run 120 ticks of MockCorridorGenerator through AegisFlowController.step()."""
    controller = AegisFlowController()
    generator = MockCorridorGenerator(seed=42)
    shield_cfg = controller.safety_shield.config

    seen_actions: set[ControlActionType] = set()
    clearance_phases = {
        SignalPhase.NS_YELLOW,
        SignalPhase.ALL_RED_TO_EW,
        SignalPhase.EW_YELLOW,
        SignalPhase.ALL_RED_TO_NS,
    }
    opposing_green = {
        SignalPhase.NS_GREEN: SignalPhase.EW_GREEN,
        SignalPhase.EW_GREEN: SignalPhase.NS_GREEN,
    }

    for frame in generator:
        forecasts, proposals, commands = controller.step(frame)

        assert set(forecasts.keys()) == {JunctionID.J_A, JunctionID.J_B, JunctionID.J_C}
        assert set(proposals.keys()) == {JunctionID.J_A, JunctionID.J_B, JunctionID.J_C}
        assert set(commands.keys()) == {JunctionID.J_A, JunctionID.J_B, JunctionID.J_C}

        for jid in JunctionID:
            state = frame[jid]
            proposal = proposals[jid]
            command = commands[jid]

            assert isinstance(forecasts[jid], SpillbackForecast)
            assert isinstance(proposal, ProposedControlAction)
            assert isinstance(command, VerifiedSignalCommand)
            assert len(proposal.reason) > 0
            seen_actions.add(proposal.action_type)

            # Verify emitted command never executes an unsafe transition or out-of-bounds green.
            if state.active_phase in opposing_green:
                assert command.approved_phase != opposing_green[state.active_phase]
            if (
                state.active_phase in clearance_phases
                and state.phase_elapsed_s < shield_cfg.all_red_duration_s
            ):
                assert command.approved_phase == state.active_phase
            if command.approved_phase in (SignalPhase.NS_GREEN, SignalPhase.EW_GREEN):
                assert command.approved_duration_s <= shield_cfg.max_green_s

    assert ControlActionType.RED_TRUNCATION in seen_actions
    assert ControlActionType.UPSTREAM_METERING in seen_actions
    assert sum(controller.safety_shield.get_audit_summary().values()) == 360
