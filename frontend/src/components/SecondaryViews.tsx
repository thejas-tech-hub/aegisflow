import { useEffect, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  Cpu,
  Radio,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
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
import type {
  ABFrameSnapshot,
  BenchmarkSummary,
  ScenarioPreset,
} from "../types/telemetry";
import { CorridorRaceCanvas } from "./CorridorRaceCanvas";
import { PredictiveHorizonStrip } from "./PredictiveHorizonStrip";

interface CorridorDetailViewProps {
  frame: ABFrameSnapshot | null;
}

export function CorridorDetailView({ frame }: CorridorDetailViewProps) {
  return (
    <div className="space-y-4">
      <div className="glass-card rounded-xl border border-slate-800/90 p-4">
        <h2 className="font-display text-sm font-semibold tracking-tight text-slate-100">
          Per-Junction 45s Predictive Horizon &amp; Heterogeneous Vehicle Mix
        </h2>
        <p className="mt-0.5 font-sans text-xs text-slate-400">
          Live BEV spatial occupancy, Indian PCU density, +45s queue projections,
          and orchestrator rationale across J_A, J_B, and J_C
        </p>
      </div>
      <PredictiveHorizonStrip aegisflow={frame?.aegisflow ?? null} />
      <CorridorRaceCanvas frame={frame} />
    </div>
  );
}

interface AnalyticsViewProps {
  scenario: ScenarioPreset;
  runBenchmark: (targetScenario?: ScenarioPreset) => Promise<BenchmarkSummary>;
}

const MONTE_CARLO_SUMMARY: readonly {
  scenario: string;
  controller: string;
  travel: string;
  stopped: string;
  peakQueue: string;
  violations: number;
}[] = [
    {
      scenario: "moderate_mixed",
      controller: "Fixed-Time",
      travel: "184.6 ± 0.6s",
      stopped: "117.6 ± 0.6s",
      peakQueue: "121.9m",
      violations: 0,
    },
    {
      scenario: "moderate_mixed",
      controller: "Isolated Local EVP",
      travel: "85.0 ± 0.0s",
      stopped: "18.0 ± 0.0s",
      peakQueue: "159.3m",
      violations: 0,
    },
    {
      scenario: "moderate_mixed",
      controller: "AegisFlow v2.0",
      travel: "67.0 ± 0.0s",
      stopped: "0.0 ± 0.0s",
      peakQueue: "100.8m",
      violations: 0,
    },
    {
      scenario: "peak_spillback",
      controller: "Fixed-Time",
      travel: "259.9 ± 0.5s",
      stopped: "192.9 ± 0.5s",
      peakQueue: "230.8m",
      violations: 0,
    },
    {
      scenario: "peak_spillback",
      controller: "Isolated Local EVP",
      travel: "112.8 ± 0.4s",
      stopped: "45.8 ± 0.4s",
      peakQueue: "278.0m",
      violations: 0,
    },
    {
      scenario: "peak_spillback",
      controller: "AegisFlow v2.0",
      travel: "71.0 ± 0.0s",
      stopped: "4.0 ± 0.0s",
      peakQueue: "198.1m",
      violations: 0,
    },
    {
      scenario: "severe_gridlock",
      controller: "Isolated Local EVP",
      travel: "300.0 ± 0.0s",
      stopped: "252.4 ± 3.1s",
      peakQueue: "300.0m",
      violations: 0,
    },
    {
      scenario: "severe_gridlock",
      controller: "AegisFlow v2.0",
      travel: "86.0 ± 0.0s",
      stopped: "19.0 ± 0.0s",
      peakQueue: "228.2m",
      violations: 0,
    },
  ];

export function AnalyticsView({ scenario, runBenchmark }: AnalyticsViewProps) {
  const [summary, setSummary] = useState<BenchmarkSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  async function loadBenchmark(): Promise<void> {
    setLoading(true);
    setError(null);
    try {
      const res = await runBenchmark(scenario);
      setSummary(res);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Unable to load live benchmark"
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadBenchmark();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario]);

  const barData = summary
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
    <div className="space-y-4">
      <div className="glass-card-cyan flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4">
        <div className="flex items-center gap-2.5">
          <BarChart3 className="h-5 w-5 text-cyan-300" />
          <div>
            <h2 className="font-display text-sm font-semibold tracking-tight text-slate-100">
              Live Episode Benchmark &amp; 30-Seed Monte Carlo Suite
            </h2>
            <p className="font-sans text-xs text-slate-400">
              Active Preset: <span className="font-mono text-slate-300">{scenario}</span> · Seed{" "}
              <span className="font-mono text-slate-300">42</span> · Verified Offline Evaluation
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void loadBenchmark()}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-400/50 bg-cyan-500/15 px-3 py-1.5 font-sans text-xs font-semibold text-cyan-200 hover:bg-cyan-500/25 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Re-run Live Benchmark
        </button>
      </div>

      {error ? (
        <div className="glass-card-crimson rounded-xl border p-4 font-mono text-xs text-rose-300">
          {error}
        </div>
      ) : null}

      {summary ? (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <div className="glass-card rounded-xl border border-slate-800/90 p-4">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-300">
              Live Side-by-Side Episode Metrics ({summary.total_ticks}s)
            </h3>
            <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950/90">
              <table className="w-full text-left font-mono text-xs">
                <thead className="border-b border-slate-800 text-slate-400">
                  <tr>
                    <th className="px-3 py-2">Metric</th>
                    <th className="px-3 py-2 text-right text-rose-300">Baseline</th>
                    <th className="px-3 py-2 text-right text-cyan-300">AegisFlow</th>
                    <th className="px-3 py-2 text-right text-emerald-300">Delta</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80 text-slate-200">
                  <tr>
                    <td className="px-3 py-2">EV Travel Time (s)</td>
                    <td className="px-3 py-2 text-right">
                      {summary.baseline_kpis.ev_travel_time_s ?? "N/A"}
                    </td>
                    <td className="px-3 py-2 text-right font-bold text-cyan-300">
                      {summary.aegisflow_kpis.ev_travel_time_s ?? "N/A"}
                    </td>
                    <td className="px-3 py-2 text-right font-bold text-emerald-400">
                      -{summary.comparison_kpis.ev_travel_time_reduction_pct.toFixed(1)}%
                    </td>
                  </tr>
                  <tr>
                    <td className="px-3 py-2">EV Stopped Time (s)</td>
                    <td className="px-3 py-2 text-right">
                      {summary.baseline_kpis.ev_stopped_time_s.toFixed(1)}
                    </td>
                    <td className="px-3 py-2 text-right font-bold text-cyan-300">
                      {summary.aegisflow_kpis.ev_stopped_time_s.toFixed(1)}
                    </td>
                    <td className="px-3 py-2 text-right font-bold text-emerald-400">
                      -{summary.comparison_kpis.ev_stopped_time_reduction_pct.toFixed(1)}%
                    </td>
                  </tr>
                  <tr>
                    <td className="px-3 py-2">Peak Queue Length (m)</td>
                    <td className="px-3 py-2 text-right">
                      {summary.baseline_kpis.peak_queue_length_m.toFixed(1)}
                    </td>
                    <td className="px-3 py-2 text-right font-bold text-cyan-300">
                      {summary.aegisflow_kpis.peak_queue_length_m.toFixed(1)}
                    </td>
                    <td className="px-3 py-2 text-right font-bold text-emerald-400">
                      -{summary.comparison_kpis.peak_queue_reduction_pct.toFixed(1)}%
                    </td>
                  </tr>
                  <tr>
                    <td className="px-3 py-2">Spillback Ticks</td>
                    <td className="px-3 py-2 text-right">
                      {summary.baseline_kpis.spillback_ticks}
                    </td>
                    <td className="px-3 py-2 text-right font-bold text-cyan-300">
                      {summary.aegisflow_kpis.spillback_ticks}
                    </td>
                    <td className="px-3 py-2 text-right font-bold text-emerald-400">
                      -{summary.comparison_kpis.spillback_ticks_reduction_pct.toFixed(1)}%
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div className="glass-card rounded-xl border border-slate-800/90 p-4">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-300">
              Baseline EVP vs. AegisFlow v2.0 Comparison
            </h3>
            <div className="h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={barData}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="4 4" />
                  <XAxis
                    dataKey="metric"
                    stroke="#64748b"
                    tick={{ fill: "#cbd5e1", fontSize: 10 }}
                  />
                  <YAxis
                    stroke="#64748b"
                    tick={{ fill: "#94a3b8", fontSize: 10 }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#020617",
                      borderColor: "#334155",
                      borderRadius: "8px",
                      fontSize: "12px",
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: "11px" }} />
                  <Bar
                    dataKey="baseline"
                    name="Baseline EVP"
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
        </div>
      ) : null}

      {/* 30-Seed Monte Carlo Benchmark Table */}
      <div className="glass-card rounded-xl border border-slate-800/90 p-4">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-200">
          30-Seed Monte Carlo Evaluation &amp; Fault-Injection Summary
        </h3>
        <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950/90">
          <table className="w-full text-left font-mono text-xs">
            <thead className="border-b border-slate-800 text-slate-400">
              <tr>
                <th className="px-3 py-2">Scenario</th>
                <th className="px-3 py-2">Controller</th>
                <th className="px-3 py-2 text-right">EV Travel (s)</th>
                <th className="px-3 py-2 text-right">EV Stopped (s)</th>
                <th className="px-3 py-2 text-right">Peak J_B Queue</th>
                <th className="px-3 py-2 text-right">Safety Violations</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {MONTE_CARLO_SUMMARY.map((row) => (
                <tr
                  key={`${row.scenario}-${row.controller}`}
                  className={
                    row.controller === "AegisFlow v2.0"
                      ? "bg-cyan-500/5 text-cyan-200"
                      : "text-slate-300"
                  }
                >
                  <td className="px-3 py-2">{row.scenario}</td>
                  <td className="px-3 py-2 font-semibold">{row.controller}</td>
                  <td className="px-3 py-2 text-right">{row.travel}</td>
                  <td className="px-3 py-2 text-right">{row.stopped}</td>
                  <td className="px-3 py-2 text-right">{row.peakQueue}</td>
                  <td className="px-3 py-2 text-right font-bold text-emerald-400">
                    {row.violations}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function HelpWalkthroughView() {
  const steps = [
    {
      step: "01",
      title: "Problem: The Spillback Trap",
      accent: "glass-card-crimson",
      badgeClass: "border-rose-500/50 bg-rose-500/15 text-rose-300",
      icon: AlertTriangle,
      body: "Conventional local EVP only triggers when an ambulance is within ~110m of a single intersection. At J_A it turns green blindly and pushes the EV directly into standing downstream queues at J_B, trapping it in spillback.",
    },
    {
      step: "02",
      title: "Inter-Junction Telemetry API",
      accent: "glass-card-cyan",
      badgeClass: "border-cyan-400/50 bg-cyan-500/15 text-cyan-300",
      icon: Radio,
      body: "CCTV perception and SUMO digital-twin nodes emit identical JunctionStatePacket Pydantic contracts. When J_A detects an EV, upstream telemetry immediately alerts J_B and J_C over the FastAPI gateway.",
    },
    {
      step: "03",
      title: "45s Physics-Informed Forecast",
      accent: "glass-card-amber",
      badgeClass: "border-amber-400/50 bg-amber-500/15 text-amber-300",
      icon: Cpu,
      body: "SpillbackPredictor computes platoon travel delay, Indian PCU-weighted queue spacing, and shockwave EV ETA 30-60s ahead. CorridorOrchestrator triggers Early Flush at J_B and Upstream Metering at J_A before gridlock forms.",
    },
    {
      step: "04",
      title: "Deterministic Safety Shield",
      accent: "glass-card-emerald",
      badgeClass: "border-emerald-400/50 bg-emerald-500/15 text-emerald-300",
      icon: ShieldCheck,
      body: "Every advisory AI action must pass 5 non-negotiable municipal invariants in strict order: MANDATORY_CLEARANCE, MAX_RED_STARVATION, CONFLICT_MUTEX, MIN_GREEN_LOCK, and DURATION_BOUNDS — guaranteeing 0 unsafe transitions.",
    },
  ] as const;

  return (
    <div className="space-y-4">
      <div className="glass-card rounded-xl border border-slate-800/90 p-4">
        <h2 className="font-display text-sm font-semibold tracking-tight text-slate-100">
          How AegisFlow Works — 4-Stage Architecture Walkthrough
        </h2>
        <p className="mt-0.5 font-sans text-xs text-slate-400">
          Shifting emergency vehicle priority from reactive isolated preemption
          to predictive, safety-verified corridor orchestration
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {steps.map(({ step, title, accent, badgeClass, icon: Icon, body }) => (
          <article key={step} className={`${accent} rounded-xl border p-5`}>
            <div className="flex items-center justify-between">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-xs font-bold ${badgeClass}`}
              >
                STEP {step}
              </span>
              <Icon className="h-5 w-5 text-slate-200" />
            </div>
            <h3 className="mt-3 font-display text-base font-bold tracking-tight text-slate-100">{title}</h3>
            <p className="mt-2 font-sans text-xs leading-relaxed text-slate-300">{body}</p>
          </article>
        ))}
      </div>
    </div>
  );
}
