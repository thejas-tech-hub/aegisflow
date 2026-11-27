import type { ReactNode } from "react";
import { Gauge, Radio, ShieldCheck, Sparkles } from "lucide-react";
import type {
  ABFrameSnapshot,
  ChartHistoryPoint,
  ControlActionType,
  JunctionID,
} from "../types/telemetry";
import { createSparklinePaths } from "./sparkline";

interface LiveCorridorInsightsProps {
  frame: ABFrameSnapshot | null;
  chartHistory: ChartHistoryPoint[];
}

const JUNCTION_ORDER: readonly JunctionID[] = ["J_A", "J_B", "J_C"];

function actionShortLabel(action: ControlActionType): {
  label: string;
  classes: string;
} {
  switch (action) {
    case "RED_TRUNCATION":
      return {
        label: "EARLY FLUSH",
        classes: "border-cyan-400/50 bg-cyan-500/20 text-cyan-200",
      };
    case "GREEN_EXTENSION":
      return {
        label: "GREEN WAVE",
        classes: "border-emerald-400/50 bg-emerald-500/20 text-emerald-200",
      };
    case "UPSTREAM_METERING":
      return {
        label: "METERING",
        classes: "border-amber-400/50 bg-amber-500/20 text-amber-200",
      };
    case "RECOVERY":
      return {
        label: "RECOVERY",
        classes: "border-purple-400/50 bg-purple-500/20 text-purple-200",
      };
    default:
      return {
        label: "HOLD",
        classes: "border-slate-700 bg-slate-800/80 text-slate-300",
      };
  }
}

function narrationPill(label: string, tone: "rose" | "cyan" | "emerald" | "amber") {
  const toneClasses = {
    rose: "border-rose-400/40 bg-rose-500/15 text-rose-200",
    cyan: "border-cyan-400/40 bg-cyan-500/15 text-cyan-100",
    emerald: "border-emerald-400/40 bg-emerald-500/15 text-emerald-100",
    amber: "border-amber-400/40 bg-amber-500/15 text-amber-100",
  }[tone];
  return (
    <strong
      className={`inline-flex whitespace-nowrap rounded-md border px-1.5 py-0.5 font-mono text-[10px] ${toneClasses}`}
    >
      {label}
    </strong>
  );
}

function buildCorridorStory(frame: ABFrameSnapshot): ReactNode {
  const base = frame.baseline;
  const aegis = frame.aegisflow;
  const pulses = aegis.active_api_packets;

  if (base.kpis.ev_completed && aegis.kpis.ev_completed) {
    return (
      <>
        Episode complete: AegisFlow cleared the corridor{" "}
        {narrationPill(
          `${frame.comparison_kpis.ev_travel_time_saved_s.toFixed(1)}s FASTER`,
          "emerald"
        )}{" "}
        with <span className="font-mono text-slate-100">0</span> safety
        violations.
      </>
    );
  }

  if (aegis.kpis.ev_completed && !base.kpis.ev_completed) {
    return (
      <>
        AegisFlow cleared the corridor in{" "}
        {narrationPill(`${aegis.kpis.ev_travel_time_s ?? frame.tick}s`, "emerald")}{" "}
        while{" "}
        {narrationPill(
          `BASELINE STALLED AT ${Math.round(base.ev_position_m)}m`,
          "rose"
        )}{" "}
        <span className="whitespace-nowrap font-mono text-[11px] text-slate-400">
          ({Math.round(base.states.J_B.queue_length_m)}m J_B queue)
        </span>
        .
      </>
    );
  }

  if (base.ev_trapped_in_spillback && !aegis.ev_trapped_in_spillback) {
    return (
      <>
        {narrationPill("BASELINE STALLED AT J_B", "rose")}{" "}
        <span className="whitespace-nowrap text-slate-400">
          (<span className="font-mono">{base.kpis.ev_stopped_time_s}s</span>{" "}
          halted;{" "}
          <span className="font-mono">
            {Math.round(base.states.J_B.queue_length_m)}m
          </span>{" "}
          queue)
        </span>{" "}
        while AegisFlow glides at{" "}
        <span className="whitespace-nowrap font-mono text-cyan-200">
          {Math.round(aegis.ev_speed_mps * 3.6)} km/h
        </span>
        .
      </>
    );
  }

  if (pulses.length > 0) {
    const primary = pulses[0];
    if (primary.type === "EV_SPILLBACK_ALERT") {
      const etaText =
        primary.eta_s !== null
          ? `ETA ${Math.round(primary.eta_s)}s`
          : "imminent EV";
      const targetAction = aegis.proposals[primary.to].action_type;
      const actionLabel =
        targetAction === "RED_TRUNCATION"
          ? "EARLY FLUSH ACTIVE"
          : actionShortLabel(targetAction).label + " ACTIVE";
      return (
        <>
          {narrationPill(`${primary.from} DETECTED EV`, "rose")}{" "}
          <span className="text-slate-500">→</span>{" "}
          {narrationPill(`API ALERT TO ${primary.to}`, "cyan")}{" "}
          <span className="text-slate-500">→</span>{" "}
          {narrationPill(`${primary.to} ${actionLabel}`, "emerald")}{" "}
          <span className="whitespace-nowrap font-mono text-[11px] text-slate-400">
            ({etaText})
          </span>
          {base.ev_trapped_in_spillback ? (
            <>
              {" "}
              <span className="text-slate-500">·</span>{" "}
              {narrationPill("BASELINE STALLED AT J_B", "rose")}
            </>
          ) : null}
        </>
      );
    }
    if (primary.type === "SPILLBACK_METERING_BACKPRESSURE") {
      return (
        <>
          {narrationPill(`${primary.from} SPILLBACK RISK`, "amber")}{" "}
          <span className="whitespace-nowrap font-mono text-[11px] text-slate-400">
            ({primary.risk_index.toFixed(2)})
          </span>{" "}
          <span className="text-slate-500">→</span>{" "}
          {narrationPill(`API ALERT TO ${primary.to}`, "cyan")}{" "}
          <span className="text-slate-500">→</span>{" "}
          {narrationPill(`${primary.to} METERING ACTIVE`, "amber")}
        </>
      );
    }
    return (
      <>
        {narrationPill(`${primary.from} HANDOFF`, "cyan")}{" "}
        <span className="text-slate-500">→</span>{" "}
        {narrationPill(`API ALERT TO ${primary.to}`, "cyan")}{" "}
        <span className="text-slate-400">
          · green wave active; safety invariants maintained.
        </span>
      </>
    );
  }

  return (
    <>
      Monitoring {narrationPill("J_A → J_B → J_C", "cyan")}: AegisFlow J_B queue{" "}
      {narrationPill(`${Math.round(aegis.states.J_B.queue_length_m)}m`, "emerald")}{" "}
      vs. Baseline{" "}
      {narrationPill(`${Math.round(base.states.J_B.queue_length_m)}m`, "rose")}.
    </>
  );
}

function TrackMiniCurve({
  values,
  color,
}: {
  values: readonly number[];
  color: string;
}) {
  const gradientId = `insight-${color.slice(1)}`;
  const { linePath, areaPath } = createSparklinePaths(values, 84, 28, 4);

  return (
    <svg viewBox="0 0 84 28" className="h-7 w-20 shrink-0 overflow-visible" aria-hidden="true">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
        <filter id={`${gradientId}-glow`} x="-30%" y="-50%" width="160%" height="200%">
          <feGaussianBlur stdDeviation="1.8" result="blur" />
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
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        filter={`url(#${gradientId}-glow)`}
      />
    </svg>
  );
}

export function LiveCorridorInsights({
  frame,
  chartHistory,
}: LiveCorridorInsightsProps) {
  if (frame === null) {
    return (
      <aside className="glass-card flex h-full flex-col justify-center rounded-xl border border-slate-800 p-5 text-center">
        <p className="font-sans text-xs text-slate-400">
          Connecting to Live Corridor Insights stream...
        </p>
      </aside>
    );
  }

  const baseSpeedKmh = Math.round(frame.baseline.ev_speed_mps * 3.6);
  const aegisSpeedKmh = Math.round(frame.aegisflow.ev_speed_mps * 3.6);
  const baseSeries = chartHistory.slice(-14).map((p) => p.baselineJbQueueM);
  const aegisSeries = chartHistory.slice(-14).map((p) => p.aegisflowJbQueueM);

  const primaryAegisStatus = frame.aegisflow.kpis.ev_completed
    ? "CLEARED"
    : frame.aegisflow.ev_trapped_in_spillback
      ? "SLOWED IN QUEUE"
      : actionShortLabel(frame.aegisflow.proposals.J_B.action_type).label;

  return (
    <aside className="glass-card flex h-full min-h-0 flex-col justify-between gap-2 rounded-xl border border-slate-800/90 p-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Radio className="h-4 w-4 animate-pulse text-cyan-400" />
          <h3 className="font-sans text-sm font-semibold tracking-tight text-slate-100">
            Live Corridor Insights
          </h3>
        </div>
        <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-lg border border-slate-700 bg-slate-950/90 px-2.5 py-1 font-sans text-[11px] font-medium text-slate-400">
          CORRIDOR TICK:{" "}
          <strong className="font-mono text-cyan-300">{frame.tick}s</strong>
        </span>
      </div>

      {/* Track A — Baseline EVP */}
      <div className="glass-card-crimson rounded-xl border p-2.5">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2.5">
            <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg border border-rose-500/40 bg-rose-500/15 text-rose-300">
              <Gauge className="h-4 w-4" />
            </div>
            <div>
              <div className="font-sans text-[11px] font-bold uppercase tracking-wider text-rose-300">
                TRACK A · BASELINE EVP
              </div>
              <div className="mt-0.5 font-mono text-sm font-bold text-slate-100">
                {frame.baseline.kpis.ev_completed
                  ? `CLEARED (${frame.baseline.kpis.ev_travel_time_s ?? frame.tick}s)`
                  : `${baseSpeedKmh} km/h · ${Math.round(frame.baseline.ev_position_m)}m`}
              </div>
            </div>
          </div>
          <TrackMiniCurve values={baseSeries} color="#fb7185" />
        </div>

        <div className="mt-2.5 flex flex-wrap items-center gap-2 font-mono text-[10px]">
          {frame.baseline.ev_trapped_in_spillback ? (
            <span className="animate-pulse whitespace-nowrap rounded-full border border-rose-400/80 bg-rose-600/80 px-2.5 py-0.5 font-bold text-white">
              TRAPPED IN SPILLBACK · {frame.baseline.kpis.ev_stopped_time_s}s halted
            </span>
          ) : frame.baseline.kpis.ev_completed ? (
            <span className="whitespace-nowrap rounded-full border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-0.5 font-semibold text-emerald-300">
              CLEARED ({frame.baseline.kpis.ev_stopped_time_s}s halted)
            </span>
          ) : (
            <span className="whitespace-nowrap rounded-full border border-slate-700 bg-slate-900/90 px-2.5 py-0.5 text-slate-300">
              MOVING · J_B queue {Math.round(frame.baseline.states.J_B.queue_length_m)}m
            </span>
          )}
        </div>
      </div>

      {/* Track B — AegisFlow v2.0 */}
      <div className="glass-card-cyan rounded-xl border p-2.5">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2.5">
            <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg border border-cyan-400/40 bg-cyan-500/15 text-cyan-300">
              <ShieldCheck className="h-4 w-4" />
            </div>
            <div>
              <div className="font-sans text-[11px] font-bold uppercase tracking-wider text-cyan-300">
                TRACK B · AEGISFLOW v2.0
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm font-bold text-slate-100">
                  {frame.aegisflow.kpis.ev_completed
                    ? `CLEARED (${frame.aegisflow.kpis.ev_travel_time_s ?? frame.tick}s)`
                    : `${aegisSpeedKmh} km/h · ${Math.round(frame.aegisflow.ev_position_m)}m`}
                </span>
                <span className="whitespace-nowrap rounded-full border border-emerald-400/50 bg-emerald-500/15 px-2 py-0.5 font-mono text-[10px] font-semibold text-emerald-300">
                  {primaryAegisStatus}
                </span>
              </div>
            </div>
          </div>
          <TrackMiniCurve values={aegisSeries} color="#22d3ee" />
        </div>

        <div className="mt-2.5 flex flex-wrap items-center gap-1.5 font-mono text-[10px]">
          {JUNCTION_ORDER.map((jid) => {
            const badge = actionShortLabel(
              frame.aegisflow.proposals[jid].action_type
            );
            return (
              <span
                key={jid}
                className={`whitespace-nowrap rounded-md border px-2 py-0.5 ${badge.classes}`}
              >
                {jid}: {badge.label}
              </span>
            );
          })}
        </div>
      </div>

      {/* Live Plain-English Story Banner */}
      <div className="rounded-xl border border-cyan-500/25 bg-slate-950/90 px-3 py-2">
        <div className="mb-1 flex items-center gap-1.5 font-sans text-[11px] font-semibold uppercase tracking-wider text-cyan-300">
          <Sparkles className="h-3 w-3" />
          Live Tactical Narration
        </div>
        <p className="font-sans text-xs leading-relaxed text-slate-200">
          {buildCorridorStory(frame)}
        </p>
      </div>
    </aside>
  );
}
