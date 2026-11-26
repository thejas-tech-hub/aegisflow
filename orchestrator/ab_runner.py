"""Side-by-side Dual-Track A/B runner comparing Baseline EVP vs. AegisFlow v2.0."""

from typing import Any

from orchestrator.baseline_evp import IsolatedEVPController
from orchestrator.controller import AegisFlowController
from orchestrator.corridor_physics import CorridorPhysicsSim, ScenarioPreset
from schemas.contracts import (
    ControlActionType,
    JunctionID,
    JunctionStatePacket,
    ProposedControlAction,
    SpillbackForecast,
)


def _pct_reduction(baseline_val: float, aegisflow_val: float) -> float:
    """Compute percentage reduction achieved by AegisFlow relative to Baseline."""
    if baseline_val <= 0.0:
        return 0.0
    return round(((baseline_val - aegisflow_val) / baseline_val) * 100.0, 2)


class DualTrackABRunner:
    """Runs identical corridor simulations side-by-side for live A/B comparison."""

    def __init__(
        self,
        scenario: ScenarioPreset = "peak_spillback",
        seed: int = 42,
    ) -> None:
        """Initialize matched Baseline EVP and AegisFlow physics & controller tracks."""
        self.scenario: ScenarioPreset = scenario
        self.seed = seed
        self.baseline_sim = CorridorPhysicsSim(scenario=scenario, seed=seed)
        self.aegisflow_sim = CorridorPhysicsSim(scenario=scenario, seed=seed)
        self.baseline_controller = IsolatedEVPController()
        self.aegisflow_controller = AegisFlowController()

    def _build_api_pulses(
        self,
        states: dict[JunctionID, JunctionStatePacket],
        forecasts: dict[JunctionID, SpillbackForecast],
        proposals: dict[JunctionID, ProposedControlAction],
    ) -> list[dict[str, Any]]:
        """Generate inter-junction API telemetry hops for frontend pulse visualization."""
        pulses: list[dict[str, Any]] = []
        pairs: tuple[tuple[JunctionID, JunctionID], ...] = (
            (JunctionID.J_A, JunctionID.J_B),
            (JunctionID.J_B, JunctionID.J_C),
        )
        for up_id, down_id in pairs:
            up_state = states[up_id]
            down_forecast = forecasts[down_id]
            up_proposal = proposals[up_id]
            down_proposal = proposals[down_id]

            if (
                up_state.ev_detected or forecasts[up_id].predicted_ev_eta_s is not None
            ) and down_forecast.predicted_ev_eta_s is not None:
                alert_type = (
                    "EV_SPILLBACK_ALERT"
                    if down_proposal.action_type == ControlActionType.RED_TRUNCATION
                    else "EV_GREEN_WAVE_HANDOFF"
                )
                pulses.append(
                    {
                        "from": up_id.value,
                        "to": down_id.value,
                        "type": alert_type,
                        "eta_s": down_forecast.predicted_ev_eta_s,
                        "risk_index": down_forecast.spillback_risk_index,
                    }
                )

            if up_proposal.action_type == ControlActionType.UPSTREAM_METERING:
                pulses.append(
                    {
                        "from": down_id.value,
                        "to": up_id.value,
                        "type": "SPILLBACK_METERING_BACKPRESSURE",
                        "eta_s": forecasts[up_id].predicted_ev_eta_s,
                        "risk_index": down_forecast.spillback_risk_index,
                    }
                )

        return pulses

    def _compute_comparison_kpis(
        self,
        base_kpis: dict[str, Any],
        aegis_kpis: dict[str, Any],
    ) -> dict[str, float]:
        """Calculate real-time percentage reductions across core benchmark KPIs."""
        base_tt = base_kpis["ev_travel_time_s"]
        aegis_tt = aegis_kpis["ev_travel_time_s"]
        if base_tt is not None and aegis_tt is not None:
            travel_reduction_pct = _pct_reduction(float(base_tt), float(aegis_tt))
            travel_saved_s = round(float(base_tt) - float(aegis_tt), 2)
        else:
            # Progress-based estimate while either track is still traversing.
            base_progress = self.baseline_sim.ev_position_m
            aegis_progress = self.aegisflow_sim.ev_position_m
            travel_reduction_pct = round(
                max(0.0, (aegis_progress - base_progress) / 9.3), 2
            )
            travel_saved_s = 0.0

        base_stop = float(base_kpis["ev_stopped_time_s"])
        aegis_stop = float(aegis_kpis["ev_stopped_time_s"])
        return {
            "ev_travel_time_reduction_pct": travel_reduction_pct,
            "ev_travel_time_saved_s": travel_saved_s,
            "ev_stopped_time_reduction_pct": _pct_reduction(base_stop, aegis_stop),
            "ev_stopped_time_saved_s": round(base_stop - aegis_stop, 2),
            "peak_queue_reduction_pct": _pct_reduction(
                float(base_kpis["peak_queue_length_m"]),
                float(aegis_kpis["peak_queue_length_m"]),
            ),
            "spillback_ticks_reduction_pct": _pct_reduction(
                float(base_kpis["spillback_ticks"]),
                float(aegis_kpis["spillback_ticks"]),
            ),
        }

    def step(self) -> dict[str, Any]:
        """Advance both simulation tracks by 1 second and emit an ABFrameSnapshot."""
        current_tick = self.baseline_sim.tick

        base_states = self.baseline_sim.get_state_packets()
        _, base_commands = self.baseline_controller.step(base_states)
        self.baseline_sim.apply_commands(base_commands)

        aegis_states = self.aegisflow_sim.get_state_packets()
        aegis_forecasts, aegis_proposals, aegis_commands = (
            self.aegisflow_controller.step(aegis_states)
        )
        self.aegisflow_sim.apply_commands(aegis_commands)

        base_kpis = {
            **self.baseline_sim.get_kpis(),
            "shield_audit_summary": self.baseline_controller.safety_shield.get_audit_summary(),
        }
        aegis_kpis = {
            **self.aegisflow_sim.get_kpis(),
            "shield_audit_summary": self.aegisflow_controller.safety_shield.get_audit_summary(),
        }
        api_pulses = self._build_api_pulses(
            aegis_states, aegis_forecasts, aegis_proposals
        )

        return {
            "tick": current_tick,
            "scenario": self.scenario,
            "baseline": {
                "states": {
                    jid.value: pkt.model_dump(mode="json")
                    for jid, pkt in base_states.items()
                },
                "commands": {
                    jid.value: cmd.model_dump(mode="json")
                    for jid, cmd in base_commands.items()
                },
                "ev_position_m": self.baseline_sim.ev_position_m,
                "ev_speed_mps": self.baseline_sim.ev_speed_mps,
                "ev_trapped_in_spillback": self.baseline_sim.ev_trapped_in_spillback,
                "kpis": base_kpis,
            },
            "aegisflow": {
                "states": {
                    jid.value: pkt.model_dump(mode="json")
                    for jid, pkt in aegis_states.items()
                },
                "forecasts": {
                    jid.value: fc.model_dump(mode="json")
                    for jid, fc in aegis_forecasts.items()
                },
                "proposals": {
                    jid.value: prop.model_dump(mode="json")
                    for jid, prop in aegis_proposals.items()
                },
                "commands": {
                    jid.value: cmd.model_dump(mode="json")
                    for jid, cmd in aegis_commands.items()
                },
                "ev_position_m": self.aegisflow_sim.ev_position_m,
                "ev_speed_mps": self.aegisflow_sim.ev_speed_mps,
                "ev_trapped_in_spillback": self.aegisflow_sim.ev_trapped_in_spillback,
                "active_api_packets": api_pulses,
                "kpis": aegis_kpis,
            },
            "comparison_kpis": self._compute_comparison_kpis(base_kpis, aegis_kpis),
        }

    def run_full_episode(self, max_ticks: int = 150) -> dict[str, Any]:
        """Run both tracks until both EVs exit the corridor or max_ticks elapses."""
        last_snapshot: dict[str, Any] = {}
        for _ in range(max_ticks):
            last_snapshot = self.step()
            if (
                self.baseline_sim.ev_completed
                and self.aegisflow_sim.ev_completed
            ):
                break

        return {
            "scenario": self.scenario,
            "total_ticks": self.baseline_sim.tick,
            "baseline_kpis": last_snapshot["baseline"]["kpis"],
            "aegisflow_kpis": last_snapshot["aegisflow"]["kpis"],
            "comparison_kpis": last_snapshot["comparison_kpis"],
            "final_snapshot": last_snapshot,
        }


def _format_cli_report(summary: dict[str, Any]) -> str:
    """Render a crisp terminal A/B benchmark summary table."""
    base = summary["baseline_kpis"]
    aegis = summary["aegisflow_kpis"]
    comp = summary["comparison_kpis"]

    lines = [
        "=" * 74,
        f"AegisFlow Dual-Track A/B Benchmark  |  Scenario: {summary['scenario']}  |  Ticks: {summary['total_ticks']}",
        "=" * 74,
        f"{'Metric':<30} | {'Baseline EVP':>14} | {'AegisFlow v2':>14} | {'Delta':>8}",
        "-" * 74,
        f"{'EV Travel Time (s)':<30} | {base['ev_travel_time_s']!s:>14} | {aegis['ev_travel_time_s']!s:>14} | -{comp['ev_travel_time_reduction_pct']:>6.1f}%",
        f"{'EV Stopped Time (s)':<30} | {base['ev_stopped_time_s']:>14.2f} | {aegis['ev_stopped_time_s']:>14.2f} | -{comp['ev_stopped_time_reduction_pct']:>6.1f}%",
        f"{'Peak Queue Length (m)':<30} | {base['peak_queue_length_m']:>14.2f} | {aegis['peak_queue_length_m']:>14.2f} | -{comp['peak_queue_reduction_pct']:>6.1f}%",
        f"{'Spillback Ticks':<30} | {base['spillback_ticks']:>14d} | {aegis['spillback_ticks']:>14d} | -{comp['spillback_ticks_reduction_pct']:>6.1f}%",
        "-" * 74,
        f"Baseline Shield Audit  : {base['shield_audit_summary']}",
        f"AegisFlow Shield Audit : {aegis['shield_audit_summary']}",
        "=" * 74,
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    runner = DualTrackABRunner(scenario="peak_spillback", seed=42)
    episode_summary = runner.run_full_episode(max_ticks=150)
    print(_format_cli_report(episode_summary))
