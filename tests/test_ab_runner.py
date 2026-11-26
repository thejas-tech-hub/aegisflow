"""Tests for DualTrackABRunner, IsolatedEVPController, and CorridorPhysicsSim."""

import json

from orchestrator.ab_runner import DualTrackABRunner
from schemas.contracts import JunctionID, SignalPhase


def test_both_tracks_start_from_identical_initial_state() -> None:
    """Baseline and AegisFlow sims must begin with identical queues and EV pose."""
    runner = DualTrackABRunner(scenario="peak_spillback", seed=42)
    base_init = runner.baseline_sim.get_state_packets()
    aegis_init = runner.aegisflow_sim.get_state_packets()

    assert runner.baseline_sim.ev_position_m == runner.aegisflow_sim.ev_position_m
    assert runner.baseline_sim.ev_position_m == -180.0
    for jid in JunctionID:
        assert base_init[jid] == aegis_init[jid]


def test_aegisflow_outperforms_baseline_evp_in_peak_spillback() -> None:
    """AegisFlow achieves strictly lower EV travel and stopped times than Baseline."""
    runner = DualTrackABRunner(scenario="peak_spillback", seed=42)
    summary = runner.run_full_episode(max_ticks=150)

    base_kpis = summary["baseline_kpis"]
    aegis_kpis = summary["aegisflow_kpis"]

    assert base_kpis["ev_completed"] is True
    assert aegis_kpis["ev_completed"] is True
    assert aegis_kpis["ev_travel_time_s"] < base_kpis["ev_travel_time_s"]
    assert aegis_kpis["ev_stopped_time_s"] < base_kpis["ev_stopped_time_s"]
    assert summary["comparison_kpis"]["ev_travel_time_reduction_pct"] > 0.0
    assert summary["comparison_kpis"]["ev_stopped_time_reduction_pct"] > 0.0


def test_both_tracks_obey_safety_shield_invariants() -> None:
    """Every applied phase change passes through DeterministicSafetyShield legally."""
    runner = DualTrackABRunner(scenario="peak_spillback", seed=42)
    opposing_green = {
        SignalPhase.NS_GREEN: SignalPhase.EW_GREEN,
        SignalPhase.EW_GREEN: SignalPhase.NS_GREEN,
    }

    prev_base_phases = {
        jid: pkt.active_phase
        for jid, pkt in runner.baseline_sim.get_state_packets().items()
    }
    prev_aegis_phases = {
        jid: pkt.active_phase
        for jid, pkt in runner.aegisflow_sim.get_state_packets().items()
    }

    ticks_run = 0
    for _ in range(150):
        snapshot = runner.step()
        ticks_run += 1

        for jid in JunctionID:
            base_phase = SignalPhase(
                snapshot["baseline"]["states"][jid.value]["active_phase"]
            )
            aegis_phase = SignalPhase(
                snapshot["aegisflow"]["states"][jid.value]["active_phase"]
            )
            if prev_base_phases[jid] in opposing_green:
                assert base_phase != opposing_green[prev_base_phases[jid]]
            if prev_aegis_phases[jid] in opposing_green:
                assert aegis_phase != opposing_green[prev_aegis_phases[jid]]

            prev_base_phases[jid] = base_phase
            prev_aegis_phases[jid] = aegis_phase

        if (
            runner.baseline_sim.ev_completed
            and runner.aegisflow_sim.ev_completed
        ):
            break

    base_audit = runner.baseline_controller.safety_shield.get_audit_summary()
    aegis_audit = runner.aegisflow_controller.safety_shield.get_audit_summary()
    assert sum(base_audit.values()) == ticks_run * 3
    assert sum(aegis_audit.values()) == ticks_run * 3


def test_step_snapshots_json_serializable_and_emit_api_pulses() -> None:
    """Every step() snapshot serializes via json.dumps() and emits API pulses."""
    runner = DualTrackABRunner(scenario="peak_spillback", seed=42)
    seen_pulse_types: set[str] = set()

    for _ in range(40):
        snapshot = runner.step()
        encoded = json.dumps(snapshot)
        assert isinstance(encoded, str) and len(encoded) > 0
        for pulse in snapshot["aegisflow"]["active_api_packets"]:
            seen_pulse_types.add(pulse["type"])

    assert "EV_SPILLBACK_ALERT" in seen_pulse_types
