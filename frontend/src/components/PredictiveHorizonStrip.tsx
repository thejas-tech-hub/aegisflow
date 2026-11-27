import { AlertTriangle, Siren } from "lucide-react";
import type {
  AegisFlowTrackSnapshot,
  JunctionID,
} from "../types/telemetry";

interface PredictiveHorizonStripProps {
  aegisflow: AegisFlowTrackSnapshot | null;
}

const JUNCTION_ORDER: readonly JunctionID[] = ["J_A", "J_B", "J_C"];
const JUNCTION_SUBTITLES: Record<JunctionID, string> = {
  J_A: "Upstream Entry (0m)",
  J_B: "Spillback Chokepoint (300m)",
  J_C: "Downstream Exit (600m)",
};

export function PredictiveHorizonStrip({
  aegisflow,
}: PredictiveHorizonStripProps) {
  if (aegisflow === null) {
    return null;
  }

  return (
    <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {JUNCTION_ORDER.map((jid) => {
        const state = aegisflow.states[jid];
        const forecast = aegisflow.forecasts[jid];
        const proposal = aegisflow.proposals[jid];

        const currentPct = Math.round(state.spatial_occupancy_ratio * 100);
        const predictedPct = Math.round(forecast.predicted_occupancy_ratio * 100);
        const spillbackRisk = forecast.spillback_risk_index;
        const imminent = forecast.spillback_imminent;
        const eta = forecast.predicted_ev_eta_s ?? state.ev_eta_s;

        return (
          <article
            key={jid}
            className={`rounded-xl border p-4 transition-colors ${
              imminent
                ? "border-rose-500/40 bg-slate-900/90 shadow-[0_0_20px_rgba(244,63,94,0.12)]"
                : "border-slate-800 bg-slate-900/80"
            }`}
          >
            {/* Card header */}
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-bold text-slate-100">
                    {jid}
                  </span>
                  <span className="text-xs text-slate-400">
                    {JUNCTION_SUBTITLES[jid]}
                  </span>
                </div>
                <p className="mt-0.5 font-mono text-[11px] text-slate-400">
                  Phase:{" "}
                  <span className="text-cyan-300">{state.active_phase}</span> (
                  {Math.round(state.phase_elapsed_s)}s)
                </p>
              </div>

              <div className="flex flex-wrap items-center justify-end gap-1.5">
                {eta !== null ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-cyan-500/40 bg-cyan-500/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-cyan-300">
                    <Siren className="h-3 w-3" />
                    ETA {eta.toFixed(1)}s
                  </span>
                ) : null}
                {imminent ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-rose-500/40 bg-rose-500/15 px-2 py-0.5 font-mono text-[11px] font-semibold text-rose-300">
                    <AlertTriangle className="h-3 w-3" />
                    RISK {spillbackRisk.toFixed(2)}
                  </span>
                ) : (
                  <span className="rounded-full border border-slate-700 bg-slate-800 px-2 py-0.5 font-mono text-[11px] text-slate-300">
                    RISK {spillbackRisk.toFixed(2)}
                  </span>
                )}
              </div>
            </div>

            {/* Dual-Layer 45s Forecast Bar */}
            <div className="mt-3">
              <div className="mb-1 flex items-center justify-between font-mono text-[11px]">
                <span className="text-slate-400">
                  Now: <strong className="text-slate-200">{currentPct}%</strong>{" "}
                  ({Math.round(state.queue_length_m)}m)
                </span>
                <span className="text-cyan-300">
                  +{forecast.horizon_s}s Forecast:{" "}
                  <strong>{predictedPct}%</strong> (
                  {Math.round(forecast.predicted_queue_length_m)}m)
                </span>
              </div>

              <div className="relative h-5 w-full overflow-hidden rounded-md border border-slate-800 bg-slate-950">
                {/* Predicted translucent ghost bar (+45s) */}
                <div
                  className={`absolute inset-y-0 left-0 transition-all duration-300 ${
                    imminent
                      ? "bg-rose-400/30 shadow-[0_0_12px_rgba(244,63,94,0.35)]"
                      : "bg-cyan-400/25 shadow-[0_0_10px_rgba(34,211,238,0.28)]"
                  }`}
                  style={{ width: `${Math.min(100, predictedPct)}%` }}
                />
                {/* Current solid occupancy bar */}
                <div
                  className={`absolute inset-y-0 left-0 transition-all duration-300 ${
                    currentPct >= 78
                      ? "bg-rose-500"
                      : currentPct >= 50
                        ? "bg-amber-500"
                        : "bg-cyan-500"
                  }`}
                  style={{ width: `${Math.min(100, currentPct)}%` }}
                />
                {/* Vertical red dashed marker at 78% spillback threshold */}
                <div
                  className="absolute inset-y-0 border-l-2 border-dashed border-rose-500"
                  style={{ left: "78%" }}
                  title="78% Spillback Threshold"
                />
              </div>
              <div className="mt-1 flex justify-end font-mono text-[10px] text-rose-400">
                78% Spillback Limit
              </div>
            </div>

            {/* Heterogeneous Indian Vehicle Mix & PCU */}
            <div className="mt-2.5 flex flex-wrap items-center gap-1.5 font-mono text-[11px]">
              <span className="rounded bg-slate-800/90 px-2 py-0.5 text-slate-300">
                Bikes {state.vehicle_mix.motorcycles}
              </span>
              <span className="rounded bg-slate-800/90 px-2 py-0.5 text-amber-300">
                Autos {state.vehicle_mix.auto_rickshaws}
              </span>
              <span className="rounded bg-slate-800/90 px-2 py-0.5 text-cyan-300">
                Cars {state.vehicle_mix.cars}
              </span>
              <span className="rounded bg-slate-800/90 px-2 py-0.5 text-rose-300">
                Buses {state.vehicle_mix.buses_trucks}
              </span>
              <span className="ml-auto rounded border border-slate-700 bg-slate-950 px-2 py-0.5 text-emerald-300">
                PCU {state.pcu_density.toFixed(1)}
              </span>
            </div>

            {/* Live Orchestrator Decision Reason */}
            <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/90 px-3 py-2">
              <div className="mb-0.5 flex items-center justify-between font-mono text-[10px] uppercase tracking-wider">
                <span className="text-cyan-400">{proposal.action_type}</span>
                <span className="text-slate-500">
                  Priority {proposal.priority_score.toFixed(2)}
                </span>
              </div>
              <p className="text-xs leading-relaxed text-slate-300">
                {proposal.reason}
              </p>
            </div>
          </article>
        );
      })}
    </section>
  );
}
