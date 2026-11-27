"""A/B benchmark: Baseline EVP vs AegisFlow on the SUMO corridor.

Runs the identical scenario with two controllers (same seed) and
compares microscopic ambulance KPIs side-by-side.

Usage:
    python -m sim.run_sumo_benchmark          # headless
    python -m sim.run_sumo_benchmark --gui    # sumo-gui (presentation)
    python -m sim.run_sumo_benchmark --seed 7 # custom seed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path for intra-package imports.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import traci  # type: ignore[import-untyped]

from orchestrator.baseline_evp import IsolatedEVPController
from orchestrator.controller import AegisFlowController
from schemas.contracts import (
    JunctionID,
    JunctionStatePacket,  # noqa: F401
    SignalPhase,  # noqa: F401
    VehicleMix,  # noqa: F401
    VerifiedSignalCommand,  # noqa: F401
)
from sim.traci_bridge import SUMOCorridorBridge

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
AMBULANCE_ID: str = "ambulance_0"
_SUMOCFG_PATH: str = str(
    Path(__file__).resolve().parent / "network" / "corridor.sumocfg"
)
_MAX_SIM_TIME: float = 300.0
_OUTPUT_DIR: Path = Path(__file__).resolve().parent / "outputs"


# ---------------------------------------------------------------------------
# Single scenario runner
# ---------------------------------------------------------------------------
def _run_scenario(
    controller_name: str,
    controller: AegisFlowController | IsolatedEVPController,
    sumocfg: str,
    seed: int,
    gui: bool,
) -> dict[str, Any]:
    """Run one full SUMO scenario and return KPI dict."""
    bridge = SUMOCorridorBridge(sumocfg_path=sumocfg, gui=gui, seed=seed)
    bridge.start()

    # KPI accumulators
    ev_entered = False
    ev_exited = False
    ev_enter_time: float = 0.0
    ev_exit_time: float = 0.0
    ev_halting_steps: int = 0
    ev_speed_sum: float = 0.0
    ev_speed_samples: int = 0
    max_jb_queue_m: float = 0.0
    spillback_steps: int = 0
    total_shield_interventions: int = 0

    try:
        while bridge.sim_time < _MAX_SIM_TIME:
            states = bridge.step()

            # --- Controller step ---
            if isinstance(controller, AegisFlowController):
                _forecasts, _proposals, commands = controller.step(states)
            else:
                _proposals, commands = controller.step(states)

            # --- Count shield interventions ---
            for cmd in commands.values():
                if cmd.shield_decision.value in ("CLIPPED", "VETOED"):
                    total_shield_interventions += 1

            # --- Apply commands ---
            bridge.apply_commands(commands)

            # --- Track ambulance KPIs ---
            try:
                all_veh = traci.vehicle.getIDList()
            except traci.exceptions.TraCIException:
                all_veh = ()

            if AMBULANCE_ID in all_veh:
                if not ev_entered:
                    ev_entered = True
                    ev_enter_time = bridge.sim_time
                amb_speed = traci.vehicle.getSpeed(AMBULANCE_ID)
                ev_speed_sum += amb_speed
                ev_speed_samples += 1
                if amb_speed < 0.1:
                    ev_halting_steps += 1
            elif ev_entered and not ev_exited:
                ev_exited = True
                ev_exit_time = bridge.sim_time

            # --- J_B queue ---
            jb_state = states.get(JunctionID.J_B)
            if jb_state is not None:
                max_jb_queue_m = max(max_jb_queue_m, jb_state.queue_length_m)
                if jb_state.queue_length_m > 200.0:
                    spillback_steps += 1

            # Stop early if ambulance has exited
            if ev_exited:
                break
    finally:
        bridge.close()

    ev_travel = ev_exit_time - ev_enter_time if ev_exited else _MAX_SIM_TIME
    ev_avg_speed = ev_speed_sum / ev_speed_samples if ev_speed_samples > 0 else 0.0

    return {
        "controller": controller_name,
        "ev_travel_time_s": round(ev_travel, 2),
        "ev_halting_time_s": round(float(ev_halting_steps), 2),
        "ev_avg_speed_mps": round(ev_avg_speed, 2),
        "max_jb_queue_m": round(max_jb_queue_m, 2),
        "spillback_steps": spillback_steps,
        "total_shield_interventions": total_shield_interventions,
    }


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------
def _print_comparison(baseline: dict[str, Any], aegis: dict[str, Any]) -> None:
    """Print a formatted side-by-side comparison table."""
    header = f"{'KPI':<30}  {'Baseline EVP':>14}  {'AegisFlow':>14}  {'Δ':>10}"
    sep = "-" * len(header)
    print(f"\n{sep}")
    print("   SUMO A/B Benchmark Results")
    print(sep)
    print(header)
    print(sep)

    for key in [
        "ev_travel_time_s",
        "ev_halting_time_s",
        "ev_avg_speed_mps",
        "max_jb_queue_m",
        "spillback_steps",
        "total_shield_interventions",
    ]:
        b_val = baseline[key]
        a_val = aegis[key]
        if isinstance(b_val, float):
            delta = a_val - b_val
            print(f"  {key:<28}  {b_val:>14.2f}  {a_val:>14.2f}  {delta:>+10.2f}")
        else:
            delta = a_val - b_val
            print(f"  {key:<28}  {b_val:>14}  {a_val:>14}  {delta:>+10}")

    print(sep)
    print()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main() -> None:
    """Run baseline and AegisFlow scenarios, compare KPIs."""
    parser = argparse.ArgumentParser(description="AegisFlow SUMO A/B Benchmark")
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch sumo-gui for visual presentation.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for SUMO (default: 42).",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  AegisFlow SUMO Corridor A/B Benchmark")
    print("=" * 60)

    # --- Run 1: Baseline EVP ---
    print("\n[Run 1] Baseline EVP (Isolated Local Preemption) …")
    baseline_ctrl = IsolatedEVPController()
    baseline_results = _run_scenario(
        controller_name="Baseline EVP",
        controller=baseline_ctrl,
        sumocfg=_SUMOCFG_PATH,
        seed=args.seed,
        gui=args.gui,
    )
    print(f"  → Baseline EVP travel time: {baseline_results['ev_travel_time_s']:.1f}s")

    # --- Run 2: AegisFlow ---
    print("\n[Run 2] AegisFlow (Predictive Corridor Orchestration) …")
    aegis_ctrl = AegisFlowController()
    aegis_results = _run_scenario(
        controller_name="AegisFlow",
        controller=aegis_ctrl,
        sumocfg=_SUMOCFG_PATH,
        seed=args.seed,
        gui=args.gui,
    )
    print(f"  → AegisFlow travel time:    {aegis_results['ev_travel_time_s']:.1f}s")

    # --- Comparison ---
    _print_comparison(baseline_results, aegis_results)

    # --- Write JSON ---
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = _OUTPUT_DIR / "sumo_benchmark_results.json"
    output_data = {
        "seed": args.seed,
        "baseline_evp": baseline_results,
        "aegisflow": aegis_results,
    }
    output_path.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
    print(f"Results written to: {output_path}")


if __name__ == "__main__":
    main()
