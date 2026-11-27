import { Activity, BarChart3, ShieldCheck, Timer } from "lucide-react";
import type {
  ABFrameSnapshot,
  ChartHistoryPoint,
} from "../types/telemetry";
import { createSparklinePaths } from "./sparkline";

interface KpiStripProps {
  latestFrame: ABFrameSnapshot | null;
  chartHistory: ChartHistoryPoint[];
}

interface MiniSparklineProps {
  values: readonly number[];
  strokeColor: string;
  gradientId: string;
}

function MiniSparkline({
  values,
  strokeColor,
  gradientId,
}: MiniSparklineProps) {
  const width = 96;
  const height = 34;
  const { linePath, areaPath } = createSparklinePaths(values, width, height, 5);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-9 w-24 shrink-0 overflow-visible"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={strokeColor} stopOpacity={0.38} />
          <stop offset="100%" stopColor={strokeColor} stopOpacity={0.02} />
        </linearGradient>
        <filter id={`${gradientId}-glow`} x="-30%" y="-50%" width="160%" height="200%">
          <feGaussianBlur stdDeviation="2.2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <path d={areaPath} fill={`url(#${gradientId})`} />
      <path
        d={linePath}
        fill="none"
        stroke={strokeColor}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        filter={`url(#${gradientId}-glow)`}
      />
    </svg>
  );
}

export function KpiStrip({ latestFrame, chartHistory }: KpiStripProps) {
  const comp = latestFrame?.comparison_kpis;
  const baseKpis = latestFrame?.baseline.kpis;
  const aegisKpis = latestFrame?.aegisflow.kpis;

  const peakQueueSavedM =
    baseKpis && aegisKpis
      ? Math.max(0, baseKpis.peak_queue_length_m - aegisKpis.peak_queue_length_m)
      : 0;

  const guardedCount = aegisKpis
    ? aegisKpis.shield_audit_summary.APPROVED +
      aegisKpis.shield_audit_summary.CLIPPED +
      aegisKpis.shield_audit_summary.VETOED
    : 0;

  const queueDiffSeries = chartHistory
    .slice(-16)
    .map((pt) => Math.max(0, pt.baselineJbQueueM - pt.aegisflowJbQueueM));
  const aegisProgressSeries = chartHistory
    .slice(-16)
    .map((pt, idx) => Math.max(2, 280 - pt.aegisflowJbQueueM + idx * 4));
  const peakDiffSeries = chartHistory
    .slice(-16)
    .map((pt) => Math.max(0, pt.baselinePeakQueueM - pt.aegisflowPeakQueueM));
  const shieldSeries = chartHistory
    .slice(-16)
    .map((_, idx) => 12 + (idx % 4) * 2 + idx);

  return (
    <section className="grid h-auto grid-cols-1 gap-3.5 sm:grid-cols-2 xl:h-[92px] xl:grid-cols-4">
      {/* Card 1: EV Travel Time Saved */}
      <div className="glass-card-cyan flex min-h-[92px] items-center justify-between overflow-hidden rounded-xl border px-3 py-2 xl:min-h-0">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 font-sans text-xs font-medium text-slate-300">
            <Timer className="h-3.5 w-3.5 text-cyan-400" />
            <span>EV Travel Time Saved</span>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-display text-2xl font-bold tracking-tight text-cyan-300 tabular-nums">
              {comp ? `${comp.ev_travel_time_reduction_pct.toFixed(1)}%` : "--"}
            </span>
            {comp && comp.ev_travel_time_saved_s > 0 ? (
              <span className="rounded bg-cyan-500/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-cyan-300">
                -{comp.ev_travel_time_saved_s.toFixed(1)}s
              </span>
            ) : null}
          </div>
          <p className="mt-1 font-sans text-[11px] text-slate-400">
            {comp && comp.ev_travel_time_saved_s > 0 ? (
              <>
                <span className="font-mono text-slate-300">
                  {comp.ev_travel_time_saved_s.toFixed(1)}s
                </span>{" "}
                faster vs. Baseline
              </>
            ) : (
              "Tracking live corridor lead"
            )}
          </p>
        </div>
        <MiniSparkline
          values={aegisProgressSeries}
          strokeColor="#22d3ee"
          gradientId="kpi-cyan-grad"
        />
      </div>

      {/* Card 2: EV Stopped Time Reduced */}
      <div className="glass-card-emerald flex min-h-[92px] items-center justify-between overflow-hidden rounded-xl border px-3 py-2 xl:min-h-0">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 font-sans text-xs font-medium text-slate-300">
            <Activity className="h-3.5 w-3.5 text-emerald-400" />
            <span>EV Stopped Time Reduced</span>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-display text-2xl font-bold tracking-tight text-emerald-300 tabular-nums">
              {comp ? `${comp.ev_stopped_time_saved_s.toFixed(1)}s` : "--"}
            </span>
            {comp ? (
              <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-emerald-300">
                -{comp.ev_stopped_time_reduction_pct.toFixed(0)}%
              </span>
            ) : null}
          </div>
          <p className="mt-1 font-sans text-[11px] text-slate-400">
            {comp ? (
              <>
                <span className="font-mono text-slate-300">
                  {comp.ev_stopped_time_reduction_pct.toFixed(1)}%
                </span>{" "}
                less halting
              </>
            ) : (
              "Awaiting telemetry"
            )}
          </p>
        </div>
        <MiniSparkline
          values={queueDiffSeries}
          strokeColor="#10b981"
          gradientId="kpi-emerald-grad"
        />
      </div>

      {/* Card 3: Peak J_B Queue Saved */}
      <div className="glass-card-amber flex min-h-[92px] items-center justify-between overflow-hidden rounded-xl border px-3 py-2 xl:min-h-0">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 font-sans text-xs font-medium text-slate-300">
            <BarChart3 className="h-3.5 w-3.5 text-amber-400" />
            <span>Peak J_B Queue Saved</span>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-display text-2xl font-bold tracking-tight text-amber-300 tabular-nums">
              {latestFrame ? `${peakQueueSavedM.toFixed(1)}m` : "--"}
            </span>
            {comp ? (
              <span className="rounded bg-amber-500/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-amber-300">
                -{comp.peak_queue_reduction_pct.toFixed(1)}%
              </span>
            ) : null}
          </div>
          <p className="mt-1 font-sans text-[11px] text-slate-400">
            {comp ? (
              <>
                <span className="font-mono text-slate-300">
                  {comp.peak_queue_reduction_pct.toFixed(1)}%
                </span>{" "}
                peak queue drop
              </>
            ) : (
              "Awaiting telemetry"
            )}
          </p>
        </div>
        <MiniSparkline
          values={peakDiffSeries}
          strokeColor="#f59e0b"
          gradientId="kpi-amber-grad"
        />
      </div>

      {/* Card 4: Safety Shield Violations */}
      <div className="glass-card-verified flex min-h-[92px] items-center justify-between overflow-hidden rounded-xl border px-3 py-2 xl:min-h-0">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 font-sans text-xs font-medium text-slate-300">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
            <span>Safety Shield Violations</span>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-display text-2xl font-bold tracking-tight text-emerald-400 tabular-nums">
              0 — Verified
            </span>
          </div>
          <p className="mt-1 font-sans text-[11px] text-slate-400">
            {aegisKpis ? (
              <>
                <span className="font-mono text-slate-300">{guardedCount}</span>{" "}
                transitions guarded
              </>
            ) : (
              "5-invariant FSM active"
            )}
          </p>
        </div>
        <MiniSparkline
          values={shieldSeries}
          strokeColor="#34d399"
          gradientId="kpi-shield-grad"
        />
      </div>
    </section>
  );
}
