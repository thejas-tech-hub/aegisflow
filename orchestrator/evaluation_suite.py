"""30-seed Monte Carlo evaluation & adversarial fault-injection suite for AegisFlow.

Compares FixedTimeController, IsolatedEVPController, and AegisFlowController
across moderate_mixed, peak_spillback, and severe_gridlock presets, plus
sensor-noise (+/-15%) and upstream API packet-drop (30%) stress experiments.
Outputs numerical reports and dark-mode publication charts under docs/benchmarks/.
"""

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

from orchestrator.baseline_evp import IsolatedEVPController
from orchestrator.controller import AegisFlowController
from orchestrator.corridor_physics import CorridorPhysicsSim, ScenarioPreset
from safety_shield.shield import DeterministicSafetyShield
from schemas.contracts import (
    ControlActionType,
    JunctionID,
    JunctionStatePacket,
    ProposedControlAction,
    SignalPhase,
    VerifiedSignalCommand,
)

_BENCHMARK_DIR = Path(__file__).resolve().parent.parent / "docs" / "benchmarks"
_SCENARIOS: tuple[ScenarioPreset, ...] = (
    "moderate_mixed",
    "peak_spillback",
    "severe_gridlock",
)
_CONTROLLERS: tuple[str, ...] = (
    "Fixed-Time",
    "Isolated Local EVP",
    "AegisFlow v2.0",
)

_FIXED_GREEN_S = 30.0
_FIXED_YELLOW_S = 3.0
_FIXED_ALL_RED_S = 2.0
_NEXT_PHASE: dict[SignalPhase, SignalPhase] = {
    SignalPhase.EW_GREEN: SignalPhase.EW_YELLOW,
    SignalPhase.EW_YELLOW: SignalPhase.ALL_RED_TO_NS,
    SignalPhase.ALL_RED_TO_NS: SignalPhase.NS_GREEN,
    SignalPhase.NS_GREEN: SignalPhase.NS_YELLOW,
    SignalPhase.NS_YELLOW: SignalPhase.ALL_RED_TO_EW,
    SignalPhase.ALL_RED_TO_EW: SignalPhase.EW_GREEN,
}
_PHASE_LIMIT_S: dict[SignalPhase, float] = {
    SignalPhase.EW_GREEN: _FIXED_GREEN_S,
    SignalPhase.EW_YELLOW: _FIXED_YELLOW_S,
    SignalPhase.ALL_RED_TO_NS: _FIXED_ALL_RED_S,
    SignalPhase.NS_GREEN: _FIXED_GREEN_S,
    SignalPhase.NS_YELLOW: _FIXED_YELLOW_S,
    SignalPhase.ALL_RED_TO_EW: _FIXED_ALL_RED_S,
}
_OPPOSING_GREEN: dict[SignalPhase, SignalPhase] = {
    SignalPhase.NS_GREEN: SignalPhase.EW_GREEN,
    SignalPhase.EW_GREEN: SignalPhase.NS_GREEN,
}
_CLEARANCE_LIMIT_S: dict[SignalPhase, float] = {
    SignalPhase.NS_YELLOW: 3.0,
    SignalPhase.EW_YELLOW: 3.0,
    SignalPhase.ALL_RED_TO_EW: 2.0,
    SignalPhase.ALL_RED_TO_NS: 2.0,
}


class FixedTimeController:
    """Standard 30s EW / 30s NS fixed-time municipal signal controller."""

    def __init__(
        self,
        safety_shield: DeterministicSafetyShield | None = None,
    ) -> None:
        """Initialize fixed-time controller backed by DeterministicSafetyShield."""
        self.safety_shield: DeterministicSafetyShield = (
            safety_shield or DeterministicSafetyShield()
        )

    def _propose_for_junction(
        self, state: JunctionStatePacket
    ) -> ProposedControlAction:
        """Follow fixed 30s/3s/2s municipal ring timing with zero preemption."""
        active = state.active_phase
        limit = _PHASE_LIMIT_S[active]
        if state.phase_elapsed_s >= limit:
            next_phase = _NEXT_PHASE[active]
            return ProposedControlAction(
                junction_id=state.junction_id,
                timestamp=state.timestamp,
                target_phase=next_phase,
                action_type=ControlActionType.RECOVERY,
                requested_duration_s=_PHASE_LIMIT_S[next_phase],
                reason=f"Fixed-time transition {active} -> {next_phase}.",
                priority_score=0.40,
            )

        remaining = limit - state.phase_elapsed_s
        duration = (
            max(10.0, remaining)
            if active in (SignalPhase.EW_GREEN, SignalPhase.NS_GREEN)
            else max(1.0, remaining)
        )
        return ProposedControlAction(
            junction_id=state.junction_id,
            timestamp=state.timestamp,
            target_phase=active,
            action_type=ControlActionType.HOLD,
            requested_duration_s=duration,
            reason=f"Fixed-time hold on {active}.",
            priority_score=0.30,
        )

    def step(
        self,
        corridor_states: dict[JunctionID, JunctionStatePacket],
    ) -> tuple[
        dict[JunctionID, ProposedControlAction],
        dict[JunctionID, VerifiedSignalCommand],
    ]:
        """Compute fixed-time proposals and verify via DeterministicSafetyShield."""
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


@dataclass
class EpisodeMetrics:
    """Single-episode evaluation outcomes."""

    ev_travel_time_s: float
    ev_stopped_time_s: float
    peak_jb_queue_m: float
    spillback_ticks: int
    safety_violations: int


def _count_transition_violations(
    prev_states: dict[JunctionID, JunctionStatePacket],
    commands: dict[JunctionID, VerifiedSignalCommand],
    shield: DeterministicSafetyShield,
) -> int:
    """Check whether any issued command violates physical municipal safety rules."""
    violations = 0
    cfg = shield.config
    for jid, prev in prev_states.items():
        cmd = commands[jid]
        active = prev.active_phase
        next_phase = cmd.approved_phase

        if active in _OPPOSING_GREEN and next_phase == _OPPOSING_GREEN[active]:
            violations += 1
        if (
            active in (SignalPhase.NS_GREEN, SignalPhase.EW_GREEN)
            and next_phase != active
            and prev.phase_elapsed_s < cfg.min_green_s
        ):
            violations += 1
        if (
            active in _CLEARANCE_LIMIT_S
            and next_phase != active
            and prev.phase_elapsed_s < _CLEARANCE_LIMIT_S[active]
        ):
            violations += 1
        if (
            next_phase in (SignalPhase.NS_GREEN, SignalPhase.EW_GREEN)
            and cmd.approved_duration_s > cfg.max_green_s
        ):
            violations += 1
    return violations


def _mean_std(values: list[float]) -> dict[str, float]:
    """Compute sample mean and population standard deviation cleanly."""
    if not values:
        return {"mean": 0.0, "std": 0.0}
    mean_val = sum(values) / len(values)
    var_val = sum((v - mean_val) ** 2 for v in values) / len(values)
    return {
        "mean": round(mean_val, 3),
        "std": round(math.sqrt(var_val), 3),
    }


def _aggregate_episodes(episodes: list[EpisodeMetrics]) -> dict[str, Any]:
    """Aggregate mean/std metrics across Monte Carlo seeds."""
    return {
        "ev_travel_time_s": _mean_std([e.ev_travel_time_s for e in episodes]),
        "ev_stopped_time_s": _mean_std([e.ev_stopped_time_s for e in episodes]),
        "peak_jb_queue_m": _mean_std([e.peak_jb_queue_m for e in episodes]),
        "spillback_ticks": _mean_std([float(e.spillback_ticks) for e in episodes]),
        "safety_violations": sum(e.safety_violations for e in episodes),
        "n_episodes": len(episodes),
    }


def inject_sensor_noise(
    states: dict[JunctionID, JunctionStatePacket],
    rng: random.Random,
    noise_bound: float = 0.15,
) -> dict[JunctionID, JunctionStatePacket]:
    """Apply bounded +/-15% Gaussian jitter to occupancy and queue length."""
    noisy: dict[JunctionID, JunctionStatePacket] = {}
    for jid, pkt in states.items():
        occ_jitter = max(-noise_bound, min(noise_bound, rng.gauss(0.0, 0.08)))
        q_jitter = max(-noise_bound, min(noise_bound, rng.gauss(0.0, 0.08)))
        noisy_occ = round(
            min(1.0, max(0.0, pkt.spatial_occupancy_ratio * (1.0 + occ_jitter))), 4
        )
        noisy_q = round(max(0.0, pkt.queue_length_m * (1.0 + q_jitter)), 2)
        noisy[jid] = pkt.model_copy(
            update={
                "spatial_occupancy_ratio": noisy_occ,
                "queue_length_m": noisy_q,
            }
        )
    return noisy


def run_single_episode(
    controller_name: str,
    scenario: ScenarioPreset,
    seed: int,
    max_ticks: int = 300,
    noise_bound: float | None = None,
    ja_packet_drop_prob: float = 0.0,
) -> EpisodeMetrics:
    """Execute one deterministic or fault-injected corridor episode."""
    sim = CorridorPhysicsSim(scenario=scenario, seed=seed)
    fault_rng = random.Random(seed * 1009 + 7)

    if controller_name == "Fixed-Time":
        controller: Any = FixedTimeController()
    elif controller_name == "Isolated Local EVP":
        controller = IsolatedEVPController()
    else:
        controller = AegisFlowController()

    peak_jb_queue_m = sim.get_state_packets()[JunctionID.J_B].queue_length_m
    safety_violations = 0
    last_known_ja: JunctionStatePacket | None = None

    for _ in range(max_ticks):
        true_states = sim.get_state_packets()
        peak_jb_queue_m = max(peak_jb_queue_m, true_states[JunctionID.J_B].queue_length_m)

        observed_states = true_states
        if noise_bound is not None:
            observed_states = inject_sensor_noise(
                observed_states, fault_rng, noise_bound=noise_bound
            )

        if controller_name in ("Fixed-Time", "Isolated Local EVP"):
            _, commands = controller.step(observed_states)
            shield = controller.safety_shield
        elif ja_packet_drop_prob > 0.0:
            # Drop upstream J_A inter-junction API packets with probability p.
            if fault_rng.random() >= ja_packet_drop_prob:
                last_known_ja = observed_states[JunctionID.J_A]
            ja_fallback = (
                last_known_ja
                if last_known_ja is not None
                else observed_states[JunctionID.J_A].model_copy(
                    update={
                        "ev_detected": False,
                        "ev_confidence": 0.0,
                        "ev_eta_s": None,
                        "ev_distance_m": None,
                        "outflow_rate_vps": 0.0,
                    }
                )
            )
            corridor_view = {
                **observed_states,
                JunctionID.J_A: ja_fallback,
            }
            forecasts = controller.predictor.predict_corridor(corridor_view)
            proposals = controller.orchestrator.decide_corridor(
                corridor_view, forecasts
            )
            commands = {
                jid: controller.safety_shield.verify(
                    true_states[jid], proposals[jid]
                )
                for jid in proposals
            }
            shield = controller.safety_shield
        else:
            _, _, commands = controller.step(observed_states)
            shield = controller.safety_shield

        safety_violations += _count_transition_violations(
            true_states, commands, shield
        )
        sim.apply_commands(commands)
        if sim.ev_completed:
            break

    kpis = sim.get_kpis()
    travel_time_s = (
        float(kpis["ev_travel_time_s"])
        if kpis["ev_travel_time_s"] is not None
        else float(max_ticks)
    )
    return EpisodeMetrics(
        ev_travel_time_s=travel_time_s,
        ev_stopped_time_s=float(kpis["ev_stopped_time_s"]),
        peak_jb_queue_m=round(peak_jb_queue_m, 2),
        spillback_ticks=int(kpis["spillback_ticks"]),
        safety_violations=safety_violations,
    )


class MonteCarloEvaluator:
    """Runs multi-seed statistical and fault-injection benchmarks for AegisFlow."""

    def __init__(
        self,
        n_seeds: int = 30,
        n_stress_seeds: int = 10,
        max_ticks: int = 300,
        output_dir: Path | None = None,
    ) -> None:
        """Configure Monte Carlo trial counts and benchmark artifact output dir."""
        self.n_seeds = n_seeds
        self.n_stress_seeds = n_stress_seeds
        self.max_ticks = max_ticks
        self.output_dir: Path = output_dir or _BENCHMARK_DIR

    def run_monte_carlo(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Evaluate all 3 controllers across all 3 scenarios for n_seeds seeds."""
        results: dict[str, dict[str, dict[str, Any]]] = {}
        for scenario in _SCENARIOS:
            results[scenario] = {}
            for controller_name in _CONTROLLERS:
                episodes = [
                    run_single_episode(
                        controller_name=controller_name,
                        scenario=scenario,
                        seed=seed,
                        max_ticks=self.max_ticks,
                    )
                    for seed in range(1, self.n_seeds + 1)
                ]
                results[scenario][controller_name] = _aggregate_episodes(episodes)
        return results

    def run_fault_injection(self) -> dict[str, dict[str, Any]]:
        """Evaluate AegisFlow under +/-15% sensor noise and 30% packet loss."""
        modes: dict[str, tuple[str, float | None, float]] = {
            "AegisFlow (Clean)": ("AegisFlow v2.0", None, 0.0),
            "AegisFlow (+/-15% Noise)": ("AegisFlow v2.0", 0.15, 0.0),
            "AegisFlow (30% Packet Drop)": ("AegisFlow v2.0", None, 0.30),
            "Baseline EVP (Clean)": ("Isolated Local EVP", None, 0.0),
        }
        stress_results: dict[str, dict[str, Any]] = {}
        for label, (ctrl_name, noise, drop_prob) in modes.items():
            episodes = [
                run_single_episode(
                    controller_name=ctrl_name,
                    scenario="peak_spillback",
                    seed=seed,
                    max_ticks=self.max_ticks,
                    noise_bound=noise,
                    ja_packet_drop_prob=drop_prob,
                )
                for seed in range(1, self.n_stress_seeds + 1)
            ]
            stress_results[label] = _aggregate_episodes(episodes)
        return stress_results

    def _build_markdown_summary(self, report: dict[str, Any]) -> str:
        """Format evaluation results into a crisp Markdown summary table."""
        mc = report["monte_carlo"]
        stress = report["fault_injection"]
        lines = [
            "# AegisFlow Monte Carlo Evaluation & Robustness Summary",
            "",
            f"- **Monte Carlo Seeds per Scenario:** `{self.n_seeds}` (seeds `1..{self.n_seeds}`)",
            f"- **Fault-Injection Seeds (`peak_spillback`):** `{self.n_stress_seeds}` (seeds `1..{self.n_stress_seeds}`)",
            "",
            "## 1. Multi-Scenario Performance Comparison (Mean ± 1σ)",
            "",
            "| Scenario | Controller | EV Travel Time (s) | EV Stopped Time (s) | Peak J_B Queue (m) | Spillback Ticks | Safety Violations |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
        for scenario in _SCENARIOS:
            for ctrl in _CONTROLLERS:
                m = mc[scenario][ctrl]
                tt = m["ev_travel_time_s"]
                st = m["ev_stopped_time_s"]
                pq = m["peak_jb_queue_m"]
                sb = m["spillback_ticks"]
                sv = m["safety_violations"]
                lines.append(
                    f"| `{scenario}` | {ctrl} | "
                    f"{tt['mean']:.2f} ± {tt['std']:.2f} | "
                    f"{st['mean']:.2f} ± {st['std']:.2f} | "
                    f"{pq['mean']:.1f} ± {pq['std']:.1f} | "
                    f"{sb['mean']:.1f} ± {sb['std']:.1f} | "
                    f"{sv} |"
                )

        lines.extend(
            [
                "",
                "## 2. Adversarial Fault-Injection Stress Test (`peak_spillback`)",
                "",
                "| Mode | EV Travel Time (s) | EV Stopped Time (s) | Peak J_B Queue (m) | Spillback Ticks | Safety Violations |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for label, m in stress.items():
            tt = m["ev_travel_time_s"]
            st = m["ev_stopped_time_s"]
            pq = m["peak_jb_queue_m"]
            sb = m["spillback_ticks"]
            sv = m["safety_violations"]
            lines.append(
                f"| {label} | "
                f"{tt['mean']:.2f} ± {tt['std']:.2f} | "
                f"{st['mean']:.2f} ± {st['std']:.2f} | "
                f"{pq['mean']:.1f} ± {pq['std']:.1f} | "
                f"{sb['mean']:.1f} ± {sb['std']:.1f} | "
                f"{sv} |"
            )

        return "\n".join(lines) + "\n"

    def _generate_charts(self, report: dict[str, Any]) -> list[Path]:
        """Render 3 dark-mode 300-DPI benchmark charts inside output_dir."""
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt

        self.output_dir.mkdir(parents=True, exist_ok=True)
        mc = report["monte_carlo"]
        stress = report["fault_injection"]

        bg_fig = "#020617"  # slate-950
        bg_ax = "#0f172a"   # slate-900
        grid_col = "#1e293b"
        text_col = "#e2e8f0"
        muted_col = "#94a3b8"
        colors = {
            "Fixed-Time": "#fb7185",        # rose-400
            "Isolated Local EVP": "#f59e0b",  # amber-500
            "AegisFlow v2.0": "#22d3ee",    # cyan-400
        }

        def _style_axis(ax: Any, title: str, ylabel: str) -> None:
            ax.set_facecolor(bg_ax)
            ax.set_title(title, color=text_col, fontsize=12, fontweight="bold", pad=12)
            ax.set_ylabel(ylabel, color=muted_col, fontsize=10)
            ax.tick_params(colors=muted_col, labelsize=9)
            ax.grid(axis="y", color=grid_col, linestyle="--", linewidth=0.7, alpha=0.8)
            ax.set_axisbelow(True)
            for spine in ("top", "right"):
                ax.spines[spine].set_visible(False)
            for spine in ("bottom", "left"):
                ax.spines[spine].set_color("#334155")

        def _label_bars(
            ax: Any,
            bars: Any,
            errs: list[float] | None = None,
            fmt: str = "{:.1f}",
        ) -> None:
            for idx, bar in enumerate(bars):
                h = bar.get_height()
                err_offset = errs[idx] if errs is not None else 0.0
                ax.annotate(
                    fmt.format(h),
                    xy=(bar.get_x() + bar.get_width() / 2.0, h + err_offset),
                    xytext=(0, 4),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    fontweight="bold",
                    color=text_col,
                )

        # Chart 1: ev_travel_time_comparison.png
        fig1, ax1 = plt.subplots(figsize=(10, 5.6), facecolor=bg_fig)
        x_pos = list(range(len(_SCENARIOS)))
        width = 0.25
        for idx, ctrl in enumerate(_CONTROLLERS):
            means = [mc[s][ctrl]["ev_travel_time_s"]["mean"] for s in _SCENARIOS]
            stds = [mc[s][ctrl]["ev_travel_time_s"]["std"] for s in _SCENARIOS]
            offsets = [x + (idx - 1) * width for x in x_pos]
            bars = ax1.bar(
                offsets,
                means,
                width=width,
                yerr=stds,
                capsize=4,
                color=colors[ctrl],
                label=ctrl,
                error_kw={"ecolor": text_col, "elinewidth": 1.1},
                alpha=0.92,
            )
            _label_bars(ax1, bars, errs=stds, fmt="{:.1f}s")

        _style_axis(
            ax1,
            f"Emergency Vehicle Travel Time Across Corridor Scenarios ({self.n_seeds} Seeds, Mean ± 1σ)",
            "EV Travel Time (s)",
        )
        ax1.set_xticks(x_pos)
        ax1.set_xticklabels([s.replace("_", " ").title() for s in _SCENARIOS], color=text_col)
        ax1.set_ylim(0, max(mc[s][c]["ev_travel_time_s"]["mean"] + mc[s][c]["ev_travel_time_s"]["std"] for s in _SCENARIOS for c in _CONTROLLERS) * 1.24)
        ax1.legend(facecolor=bg_ax, edgecolor="#334155", labelcolor=text_col, frameon=True)
        path1 = self.output_dir / "ev_travel_time_comparison.png"
        fig1.tight_layout()
        fig1.savefig(path1, dpi=300, facecolor=bg_fig)
        plt.close(fig1)

        # Chart 2: spillback_and_halting_reduction.png
        fig2, (ax2a, ax2b) = plt.subplots(1, 2, figsize=(12.5, 5.4), facecolor=bg_fig)
        for idx, ctrl in enumerate(_CONTROLLERS):
            offsets = [x + (idx - 1) * width for x in x_pos]
            stop_means = [mc[s][ctrl]["ev_stopped_time_s"]["mean"] for s in _SCENARIOS]
            stop_stds = [mc[s][ctrl]["ev_stopped_time_s"]["std"] for s in _SCENARIOS]
            bars_a = ax2a.bar(
                offsets,
                stop_means,
                width=width,
                yerr=stop_stds,
                capsize=3,
                color=colors[ctrl],
                label=ctrl,
                error_kw={"ecolor": text_col, "elinewidth": 1.0},
                alpha=0.92,
            )
            _label_bars(ax2a, bars_a, errs=stop_stds, fmt="{:.1f}s")

            sb_means = [mc[s][ctrl]["spillback_ticks"]["mean"] for s in _SCENARIOS]
            sb_stds = [mc[s][ctrl]["spillback_ticks"]["std"] for s in _SCENARIOS]
            bars_b = ax2b.bar(
                offsets,
                sb_means,
                width=width,
                yerr=sb_stds,
                capsize=3,
                color=colors[ctrl],
                label=ctrl,
                error_kw={"ecolor": text_col, "elinewidth": 1.0},
                alpha=0.92,
            )
            _label_bars(ax2b, bars_b, errs=sb_stds, fmt="{:.1f}")

        _style_axis(ax2a, "EV Stopped / Halting Time (s)", "Stopped Time (s)")
        ax2a.set_xticks(x_pos)
        ax2a.set_xticklabels([s.replace("_", "\n").title() for s in _SCENARIOS], color=text_col)
        ax2a.set_ylim(0, max(mc[s][c]["ev_stopped_time_s"]["mean"] + mc[s][c]["ev_stopped_time_s"]["std"] for s in _SCENARIOS for c in _CONTROLLERS) * 1.25 + 1.0)
        ax2a.legend(facecolor=bg_ax, edgecolor="#334155", labelcolor=text_col, fontsize=8)

        _style_axis(ax2b, "Corridor Spillback Duration (Ticks >= 0.78 Occ)", "Spillback Ticks")
        ax2b.set_xticks(x_pos)
        ax2b.set_xticklabels([s.replace("_", "\n").title() for s in _SCENARIOS], color=text_col)
        ax2b.set_ylim(0, max(mc[s][c]["spillback_ticks"]["mean"] + mc[s][c]["spillback_ticks"]["std"] for s in _SCENARIOS for c in _CONTROLLERS) * 1.25 + 2.0)
        ax2b.legend(facecolor=bg_ax, edgecolor="#334155", labelcolor=text_col, fontsize=8)

        path2 = self.output_dir / "spillback_and_halting_reduction.png"
        fig2.tight_layout()
        fig2.savefig(path2, dpi=300, facecolor=bg_fig)
        plt.close(fig2)

        # Chart 3: fault_injection_robustness.png
        fig3, ax3 = plt.subplots(figsize=(10.5, 5.6), facecolor=bg_fig)
        stress_labels = list(stress.keys())
        stress_colors = ["#22d3ee", "#38bdf8", "#a78bfa", "#f59e0b"]
        sx = list(range(len(stress_labels)))
        s_width = 0.36

        tt_means = [stress[k]["ev_travel_time_s"]["mean"] for k in stress_labels]
        tt_stds = [stress[k]["ev_travel_time_s"]["std"] for k in stress_labels]
        st_means = [stress[k]["ev_stopped_time_s"]["mean"] for k in stress_labels]
        st_stds = [stress[k]["ev_stopped_time_s"]["std"] for k in stress_labels]

        bars_tt = ax3.bar(
            [x - s_width / 2 for x in sx],
            tt_means,
            width=s_width,
            yerr=tt_stds,
            capsize=4,
            color=stress_colors,
            error_kw={"ecolor": text_col, "elinewidth": 1.0},
            label="EV Travel Time (s)",
            alpha=0.92,
        )
        bars_st = ax3.bar(
            [x + s_width / 2 for x in sx],
            st_means,
            width=s_width,
            yerr=st_stds,
            capsize=4,
            color=["#0891b2", "#0284c7", "#7c3aed", "#d97706"],
            hatch="//",
            edgecolor=bg_fig,
            error_kw={"ecolor": text_col, "elinewidth": 1.0},
            label="EV Stopped Time (s)",
            alpha=0.88,
        )
        _label_bars(ax3, bars_tt, errs=tt_stds, fmt="{:.1f}s")
        _label_bars(ax3, bars_st, errs=st_stds, fmt="{:.1f}s")

        _style_axis(
            ax3,
            f"Fault-Injection Robustness on Peak Spillback ({self.n_stress_seeds} Seeds, Mean ± 1σ)",
            "Duration (seconds)",
        )
        ax3.set_xticks(sx)
        ax3.set_xticklabels(stress_labels, color=text_col, fontsize=9)
        ax3.set_ylim(0, max(tt_means) * 1.24)
        ax3.legend(facecolor=bg_ax, edgecolor="#334155", labelcolor=text_col)
        path3 = self.output_dir / "fault_injection_robustness.png"
        fig3.tight_layout()
        fig3.savefig(path3, dpi=300, facecolor=bg_fig)
        plt.close(fig3)

        return [path1, path2, path3]

    def run_all(self, generate_artifacts: bool = True) -> dict[str, Any]:
        """Run Monte Carlo + fault-injection suites and optionally write reports/charts."""
        monte_carlo = self.run_monte_carlo()
        fault_injection = self.run_fault_injection()
        report: dict[str, Any] = {
            "n_seeds": self.n_seeds,
            "n_stress_seeds": self.n_stress_seeds,
            "monte_carlo": monte_carlo,
            "fault_injection": fault_injection,
        }

        if generate_artifacts:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            json_path = self.output_dir / "evaluation_report.json"
            md_path = self.output_dir / "EVALUATION_SUMMARY.md"
            json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            md_path.write_text(
                self._build_markdown_summary(report), encoding="utf-8"
            )
            self._generate_charts(report)

        return report


def _format_stdout_table(report: dict[str, Any]) -> str:
    """Render concise terminal tables for Monte Carlo & fault-injection runs."""
    mc = report["monte_carlo"]
    stress = report["fault_injection"]
    lines = [
        "=" * 96,
        f"AegisFlow Monte Carlo Benchmark ({report['n_seeds']} seeds/scenario)",
        "=" * 96,
        f"{'Scenario':<17} | {'Controller':<20} | {'Travel (s)':>15} | {'Stopped (s)':>15} | {'Peak J_B (m)':>13} | {'Viol':>4}",
        "-" * 96,
    ]
    for scenario in _SCENARIOS:
        for ctrl in _CONTROLLERS:
            m = mc[scenario][ctrl]
            tt = f"{m['ev_travel_time_s']['mean']:.1f}+/-{m['ev_travel_time_s']['std']:.1f}"
            st = f"{m['ev_stopped_time_s']['mean']:.1f}+/-{m['ev_stopped_time_s']['std']:.1f}"
            pq = f"{m['peak_jb_queue_m']['mean']:.1f}+/-{m['peak_jb_queue_m']['std']:.1f}"
            lines.append(
                f"{scenario:<17} | {ctrl:<20} | {tt:>15} | {st:>15} | {pq:>13} | {m['safety_violations']:>4d}"
            )

    lines.extend(
        [
            "-" * 96,
            f"Fault-Injection Stress Suite on peak_spillback ({report['n_stress_seeds']} seeds)",
            "-" * 96,
        ]
    )
    for label, m in stress.items():
        tt = f"{m['ev_travel_time_s']['mean']:.1f}+/-{m['ev_travel_time_s']['std']:.1f}"
        st = f"{m['ev_stopped_time_s']['mean']:.1f}+/-{m['ev_stopped_time_s']['std']:.1f}"
        pq = f"{m['peak_jb_queue_m']['mean']:.1f}+/-{m['peak_jb_queue_m']['std']:.1f}"
        lines.append(
            f"{'peak_spillback':<17} | {label:<20} | {tt:>15} | {st:>15} | {pq:>13} | {m['safety_violations']:>4d}"
        )
    lines.append("=" * 96)
    return "\n".join(lines)


if __name__ == "__main__":
    evaluator = MonteCarloEvaluator(n_seeds=30, n_stress_seeds=10)
    full_report = evaluator.run_all(generate_artifacts=True)
    print(_format_stdout_table(full_report))
