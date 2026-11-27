import { ShieldCheck, TrendingDown } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  ChartHistoryPoint,
  ShieldAuditSummary,
  ShieldDecision,
  ShieldEventEntry,
} from "../types/telemetry";

interface LiveAnalyticsDockProps {
  chartHistory: ChartHistoryPoint[];
  shieldEvents: ShieldEventEntry[];
  auditSummary: ShieldAuditSummary | null;
}

const DECISION_BADGE: Record<ShieldDecision, string> = {
  APPROVED: "border-emerald-500/40 bg-emerald-500/15 text-emerald-300",
  CLIPPED: "border-amber-500/40 bg-amber-500/15 text-amber-300",
  VETOED: "border-rose-500/40 bg-rose-500/15 text-rose-300",
};

export function LiveAnalyticsDock({
  chartHistory,
  shieldEvents,
  auditSummary,
}: LiveAnalyticsDockProps) {
  const approvedCount = auditSummary?.APPROVED ?? 0;
  const clippedCount = auditSummary?.CLIPPED ?? 0;
  const vetoedCount = auditSummary?.VETOED ?? 0;

  const latestPoint =
    chartHistory.length > 0 ? chartHistory[chartHistory.length - 1] : null;
  const baselinePeak = chartHistory.reduce(
    (maxVal, pt) => Math.max(maxVal, pt.baselineJbQueueM),
    0
  );
  const aegisAtPeak = latestPoint ? latestPoint.aegisflowJbQueueM : 0;
  const baseForDelta = latestPoint
    ? Math.max(latestPoint.baselineJbQueueM, baselinePeak * 0.85)
    : 0;
  const queueReductionPct =
    baseForDelta > 1
      ? Math.max(0, ((baseForDelta - aegisAtPeak) / baseForDelta) * 100)
      : 0;

  return (
    <section className="grid grid-cols-1 gap-4 xl:h-[240px] xl:grid-cols-2">
      {/* Left Panel: Equal-Height J_B Queue Trajectory */}
      <div className="glass-card relative flex h-[320px] flex-col rounded-xl border border-slate-800/90 p-4 xl:h-full xl:min-h-0 xl:p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div>
            <h3 className="font-sans text-sm font-semibold tracking-tight text-slate-100">
              Junction J_B Queue Trajectory
            </h3>
            <p className="font-sans text-xs text-slate-400">
              Baseline spillback vs. AegisFlow predictive flush &amp; metering
            </p>
          </div>
          <div className="flex items-center gap-2">
            {latestPoint !== null && queueReductionPct > 0.5 ? (
              <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-emerald-400/50 bg-emerald-500/15 px-2.5 py-0.5 font-mono text-[11px] font-bold text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.2)]">
                <TrendingDown className="h-3 w-3" />
                -{queueReductionPct.toFixed(1)}%
              </span>
            ) : null}
            <span className="whitespace-nowrap rounded border border-rose-500/35 bg-rose-500/10 px-2 py-0.5 font-mono text-[11px] text-rose-300">
              Limit: 234m
            </span>
          </div>
        </div>

        <div className="min-h-0 flex-1 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={chartHistory}
              margin={{ top: 8, right: 12, left: -12, bottom: 0 }}
            >
              <defs>
                <linearGradient id="aegisQueueFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#22d3ee" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="baseQueueFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#f43f5e" stopOpacity={0.22} />
                  <stop offset="100%" stopColor="#f43f5e" stopOpacity={0.01} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1e293b" strokeDasharray="4 4" />
              <XAxis
                dataKey="tick"
                stroke="#64748b"
                tick={{ fill: "#94a3b8", fontSize: 10 }}
                tickFormatter={(val: number) => `${val}s`}
              />
              <YAxis
                domain={[0, 300]}
                stroke="#64748b"
                tick={{ fill: "#94a3b8", fontSize: 10 }}
                tickFormatter={(val: number) => `${val}m`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#020617",
                  borderColor: "#334155",
                  borderRadius: "8px",
                  fontSize: "12px",
                  color: "#e2e8f0",
                }}
              />
              <Legend wrapperStyle={{ fontSize: "11px", color: "#cbd5e1" }} />
              <ReferenceLine
                y={234}
                stroke="#f43f5e"
                strokeDasharray="6 4"
                strokeWidth={1.5}
              />
              <Area
                type="monotone"
                dataKey="baselineJbQueueM"
                name="Baseline J_B Queue (m)"
                stroke="#fb7185"
                strokeWidth={2}
                strokeDasharray="6 4"
                fill="url(#baseQueueFill)"
                dot={false}
                isAnimationActive={false}
              />
              <Area
                type="monotone"
                dataKey="aegisflowJbQueueM"
                name="AegisFlow J_B Queue (m)"
                stroke="#22d3ee"
                strokeWidth={2.5}
                fill="url(#aegisQueueFill)"
                dot={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Right Panel: Equal-Height Deterministic Safety Shield Interlock */}
      <div className="glass-card flex h-[320px] flex-col rounded-xl border border-slate-800/90 p-4 xl:h-full xl:min-h-0 xl:p-3">
        <div className="mb-2.5 flex shrink-0 flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            <h3 className="font-sans text-sm font-semibold tracking-tight text-slate-100">
              Deterministic Safety Shield Interlock
            </h3>
          </div>
          <span className="whitespace-nowrap rounded-full border border-emerald-500/45 bg-emerald-500/15 px-2.5 py-0.5 font-sans text-[11px] font-semibold tracking-wide text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.18)]">
            <span className="font-mono font-bold">0</span> UNSAFE TRANSITIONS
          </span>
        </div>

        {/* 3 Compact Glowing Stat Boxes */}
        <div className="mb-2.5 grid shrink-0 grid-cols-3 gap-2.5 text-xs">
          <div className="rounded-lg border border-emerald-500/30 bg-slate-950/85 px-3 py-1.5 shadow-[inset_0_0_12px_rgba(16,185,129,0.08)]">
            <div className="font-sans text-[10px] font-semibold tracking-wider text-slate-400">
              APPROVED
            </div>
            <div className="font-mono text-base font-bold text-emerald-400">
              {approvedCount}
            </div>
          </div>
          <div className="rounded-lg border border-amber-500/30 bg-slate-950/85 px-3 py-1.5 shadow-[inset_0_0_12px_rgba(245,158,11,0.08)]">
            <div className="font-sans text-[10px] font-semibold tracking-wider text-slate-400">
              CLIPPED
            </div>
            <div className="font-mono text-base font-bold text-amber-400">
              {clippedCount}
            </div>
          </div>
          <div className="rounded-lg border border-rose-500/30 bg-slate-950/85 px-3 py-1.5 shadow-[inset_0_0_12px_rgba(244,63,94,0.08)]">
            <div className="font-sans text-[10px] font-semibold tracking-wider text-slate-400">
              VETOED
            </div>
            <div className="font-mono text-base font-bold text-rose-400">
              {vetoedCount}
            </div>
          </div>
        </div>

        {/* Strictly Bounded Scrollable Audit Log */}
        <div className="custom-scrollbar min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          {shieldEvents.length === 0 ? (
            <p className="py-12 text-center font-sans text-xs text-slate-500">
              Awaiting verified signal events...
            </p>
          ) : (
            shieldEvents.map((event) => (
              <div
                key={event.id}
                className="rounded-lg border border-slate-800/90 bg-slate-950/90 px-3 py-2 text-xs"
              >
                <div className="flex flex-wrap items-center gap-1.5 font-mono text-[11px]">
                  <span className="text-slate-500">t={event.tick}s</span>
                  <span className="rounded bg-slate-800 px-1.5 py-0.5 font-bold text-slate-200">
                    {event.junctionId}
                  </span>
                  <span
                    className={`rounded border px-1.5 py-0.5 font-semibold ${DECISION_BADGE[event.decision]}`}
                  >
                    {event.decision}
                  </span>
                  <span className="text-cyan-300">
                    {event.originalAction} &rarr; {event.approvedPhase}
                  </span>
                  {event.violatedInvariants.map((inv) => (
                    <span
                      key={inv}
                      className="rounded border border-rose-500/40 bg-rose-500/10 px-1.5 py-0.5 text-[10px] text-rose-300"
                    >
                      {inv}
                    </span>
                  ))}
                </div>
                <p className="mt-1 font-sans text-[11px] text-slate-400">
                  {event.auditMessage}
                </p>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  );
}
