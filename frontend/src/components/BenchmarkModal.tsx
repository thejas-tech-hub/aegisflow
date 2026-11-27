import { useEffect, useState } from "react";
import { BarChart3, RefreshCw, X } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { BenchmarkSummary, ScenarioPreset } from "../types/telemetry";

interface BenchmarkModalProps {
  isOpen: boolean;
  scenario: ScenarioPreset;
  onClose: () => void;
  runBenchmark: (targetScenario?: ScenarioPreset) => Promise<BenchmarkSummary>;
}

interface BenchmarkBarDatum {
  metric: string;
  baseline: number;
  aegisflow: number;
}

export function BenchmarkModal({
  isOpen,
  scenario,
  onClose,
  runBenchmark,
}: BenchmarkModalProps) {
  const [summary, setSummary] = useState<BenchmarkSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  async function executeBenchmark(): Promise<void> {
    setLoading(true);
    setError(null);
    try {
      const result = await runBenchmark(scenario);
      setSummary(result);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to run A/B benchmark"
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (isOpen) {
      void executeBenchmark();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, scenario]);

  if (!isOpen) {
    return null;
  }

  const chartData: BenchmarkBarDatum[] = summary
    ? [
        {
          metric: "EV Travel (s)",
          baseline: summary.baseline_kpis.ev_travel_time_s ?? summary.total_ticks,
          aegisflow:
            summary.aegisflow_kpis.ev_travel_time_s ?? summary.total_ticks,
        },
        {
          metric: "EV Stopped (s)",
          baseline: summary.baseline_kpis.ev_stopped_time_s,
          aegisflow: summary.aegisflow_kpis.ev_stopped_time_s,
        },
        {
          metric: "Peak Queue (m)",
          baseline: summary.baseline_kpis.peak_queue_length_m,
          aegisflow: summary.aegisflow_kpis.peak_queue_length_m,
        },
        {
          metric: "Spillback Ticks",
          baseline: summary.baseline_kpis.spillback_ticks,
          aegisflow: summary.aegisflow_kpis.spillback_ticks,
        },
      ]
    : [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Full A/B Benchmark Comparison"
    >
      <div className="max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-2xl border border-cyan-500/30 bg-slate-900 p-6 shadow-[0_0_50px_rgba(34,211,238,0.16)]">
        <div className="mb-4 flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2.5">
            <BarChart3 className="h-5 w-5 text-cyan-400" />
            <div>
              <h2 className="font-display text-base font-bold tracking-tight text-slate-100">
                Full Episode A/B Benchmark Report
              </h2>
              <p className="font-sans text-xs text-slate-400">
                Scenario: <span className="font-mono text-slate-300">{scenario}</span> · Seed:{" "}
                <span className="font-mono text-slate-300">42</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void executeBenchmark()}
              disabled={loading}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:border-cyan-500/50 hover:text-cyan-300 disabled:opacity-50"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`}
              />
              Re-run
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 bg-slate-800 p-1.5 text-slate-400 hover:text-slate-100"
              aria-label="Close benchmark modal"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {loading ? (
          <div className="py-16 text-center font-sans text-sm text-cyan-300">
            Running deterministic DualTrackABRunner episode...
          </div>
        ) : error ? (
          <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 font-sans text-sm text-rose-300">
            {error}
          </div>
        ) : summary ? (
          <div className="space-y-6">
            <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950">
              <table className="w-full text-left font-mono text-xs">
                <thead className="border-b border-slate-800 bg-slate-900/90 text-slate-400">
                  <tr>
                    <th className="px-4 py-2.5">Metric</th>
                    <th className="px-4 py-2.5 text-right text-rose-300">
                      Baseline EVP
                    </th>
                    <th className="px-4 py-2.5 text-right text-cyan-300">
                      AegisFlow v2.0
                    </th>
                    <th className="px-4 py-2.5 text-right text-emerald-300">
                      Improvement
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80 text-slate-200">
                  <tr>
                    <td className="px-4 py-2.5">EV Travel Time (s)</td>
                    <td className="px-4 py-2.5 text-right">
                      {summary.baseline_kpis.ev_travel_time_s ?? "N/A"}
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold text-cyan-300">
                      {summary.aegisflow_kpis.ev_travel_time_s ?? "N/A"}
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold text-emerald-400">
                      -{summary.comparison_kpis.ev_travel_time_reduction_pct.toFixed(1)}%
                    </td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2.5">EV Stopped Time (s)</td>
                    <td className="px-4 py-2.5 text-right">
                      {summary.baseline_kpis.ev_stopped_time_s.toFixed(1)}
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold text-cyan-300">
                      {summary.aegisflow_kpis.ev_stopped_time_s.toFixed(1)}
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold text-emerald-400">
                      -{summary.comparison_kpis.ev_stopped_time_reduction_pct.toFixed(1)}%
                    </td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2.5">Peak Queue Length (m)</td>
                    <td className="px-4 py-2.5 text-right">
                      {summary.baseline_kpis.peak_queue_length_m.toFixed(1)}
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold text-cyan-300">
                      {summary.aegisflow_kpis.peak_queue_length_m.toFixed(1)}
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold text-emerald-400">
                      -{summary.comparison_kpis.peak_queue_reduction_pct.toFixed(1)}%
                    </td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2.5">Spillback Ticks</td>
                    <td className="px-4 py-2.5 text-right">
                      {summary.baseline_kpis.spillback_ticks}
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold text-cyan-300">
                      {summary.aegisflow_kpis.spillback_ticks}
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold text-emerald-400">
                      -{summary.comparison_kpis.spillback_ticks_reduction_pct.toFixed(1)}%
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="h-64 w-full rounded-xl border border-slate-800 bg-slate-950 p-3">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="4 4" />
                  <XAxis
                    dataKey="metric"
                    stroke="#64748b"
                    tick={{ fill: "#cbd5e1", fontSize: 11 }}
                  />
                  <YAxis
                    stroke="#64748b"
                    tick={{ fill: "#94a3b8", fontSize: 11 }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#020617",
                      borderColor: "#334155",
                      borderRadius: "8px",
                      fontSize: "12px",
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: "12px" }} />
                  <Bar
                    dataKey="baseline"
                    name="Baseline Isolated EVP"
                    fill="#fb7185"
                    radius={[4, 4, 0, 0]}
                  />
                  <Bar
                    dataKey="aegisflow"
                    name="AegisFlow v2.0"
                    fill="#22d3ee"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
