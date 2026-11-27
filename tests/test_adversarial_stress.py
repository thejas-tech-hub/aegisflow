"""Adversarial stress and Monte Carlo verification tests for AegisFlow."""

import random

from orchestrator.controller import AegisFlowController
from orchestrator.corridor_physics import CorridorPhysicsSim
from orchestrator.evaluation_suite import (
    MonteCarloEvaluator,
    run_single_episode,
)
from schemas.contracts import JunctionID, JunctionStatePacket


def test_aegisflow_survives_15pct_sensor_noise_and_beats_evp() -> None:
    """Under +/-15% sensor noise, AegisFlow has zero violations and beats EVP."""
    evp_metrics = run_single_episode(
        controller_name="Isolated Local EVP",
        scenario="peak_spillback",
        seed=42,
    )
    noisy_aegis = run_single_episode(
        controller_name="AegisFlow v2.0",
        scenario="peak_spillback",
        seed=42,
        noise_bound=0.15,
    )

    assert noisy_aegis.safety_violations == 0
    assert noisy_aegis.ev_stopped_time_s < evp_metrics.ev_stopped_time_s
    assert noisy_aegis.ev_travel_time_s < evp_metrics.ev_travel_time_s


def test_aegisflow_graceful_under_30pct_api_packet_drop() -> None:
    """Under 30% dropped J_A packets, AegisFlow runs cleanly with zero violations."""
    evp_metrics = run_single_episode(
        controller_name="Isolated Local EVP",
        scenario="peak_spillback",
        seed=7,
    )
    dropped_aegis = run_single_episode(
        controller_name="AegisFlow v2.0",
        scenario="peak_spillback",
        seed=7,
        ja_packet_drop_prob=0.30,
    )

    assert dropped_aegis.safety_violations == 0
    assert dropped_aegis.ev_stopped_time_s < evp_metrics.ev_stopped_time_s

    # Also verify AegisFlowController.step() directly accepts stale J_A packets cleanly.
    sim = CorridorPhysicsSim(scenario="peak_spillback", seed=7)
    controller = AegisFlowController()
    rng = random.Random(99)
    stale_ja: JunctionStatePacket | None = None
    for _ in range(40):
        states = sim.get_state_packets()
        if stale_ja is None or rng.random() >= 0.30:
            stale_ja = states[JunctionID.J_A]
        corridor_view = {**states, JunctionID.J_A: stale_ja}
        forecasts, proposals, commands = controller.step(corridor_view)
        assert set(forecasts.keys()) == {JunctionID.J_A, JunctionID.J_B, JunctionID.J_C}
        assert set(proposals.keys()) == {JunctionID.J_A, JunctionID.J_B, JunctionID.J_C}
        assert set(commands.keys()) == {JunctionID.J_A, JunctionID.J_B, JunctionID.J_C}
        sim.apply_commands({**commands, JunctionID.J_A: controller.safety_shield.verify(states[JunctionID.J_A], proposals[JunctionID.J_A])})


def test_monte_carlo_evaluator_3_seed_smoke_test() -> None:
    """Fast 3-seed MonteCarloEvaluator run confirms AegisFlow beats Fixed & EVP."""
    evaluator = MonteCarloEvaluator(n_seeds=3, n_stress_seeds=2)
    report = evaluator.run_all(generate_artifacts=False)

    peak = report["monte_carlo"]["peak_spillback"]
    fixed = peak["Fixed-Time"]
    evp = peak["Isolated Local EVP"]
    aegis = peak["AegisFlow v2.0"]

    assert aegis["safety_violations"] == 0
    assert evp["safety_violations"] == 0
    assert fixed["safety_violations"] == 0
    assert aegis["ev_travel_time_s"]["mean"] < evp["ev_travel_time_s"]["mean"]
    assert aegis["ev_travel_time_s"]["mean"] < fixed["ev_travel_time_s"]["mean"]
    assert aegis["ev_stopped_time_s"]["mean"] < evp["ev_stopped_time_s"]["mean"]
    assert aegis["ev_stopped_time_s"]["mean"] < fixed["ev_stopped_time_s"]["mean"]
