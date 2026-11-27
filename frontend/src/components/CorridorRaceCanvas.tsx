import type {
  ABFrameSnapshot,
  ApiPulsePacket,
  ControlActionType,
  JunctionID,
  JunctionStatePacket,
  ProposedControlAction,
  SignalPhase,
} from "../types/telemetry";

interface CorridorRaceCanvasProps {
  frame: ABFrameSnapshot | null;
}

const JUNCTION_COORDS: Record<JunctionID, number> = {
  J_A: 0,
  J_B: 300,
  J_C: 600,
};
const JUNCTION_ORDER: readonly JunctionID[] = ["J_A", "J_B", "J_C"];

const CORRIDOR_MIN_M = -180;
const CORRIDOR_MAX_M = 750;
const SVG_ROAD_LEFT = 68;
const SVG_ROAD_RIGHT = 1052;
const SVG_ROAD_WIDTH = SVG_ROAD_RIGHT - SVG_ROAD_LEFT;

function mapCorridorX(meters: number): number {
  const clamped = Math.max(CORRIDOR_MIN_M, Math.min(CORRIDOR_MAX_M, meters));
  const ratio = (clamped - CORRIDOR_MIN_M) / (CORRIDOR_MAX_M - CORRIDOR_MIN_M);
  return SVG_ROAD_LEFT + ratio * SVG_ROAD_WIDTH;
}

function mapQueueWidth(queueMeters: number): number {
  const ratio = Math.max(0, Math.min(300, queueMeters)) / (CORRIDOR_MAX_M - CORRIDOR_MIN_M);
  return ratio * SVG_ROAD_WIDTH;
}

function getArterialSignalColor(phase: SignalPhase): string {
  if (phase === "EW_GREEN") {
    return "#10b981";
  }
  if (phase === "EW_YELLOW") {
    return "#f59e0b";
  }
  return "#f43f5e";
}

function getCrossSignalColor(phase: SignalPhase): string {
  if (phase === "NS_GREEN") {
    return "#10b981";
  }
  if (phase === "NS_YELLOW") {
    return "#f59e0b";
  }
  return "#f43f5e";
}

function getQueueColor(occupancy: number): string {
  if (occupancy >= 0.78) {
    return "#f43f5e";
  }
  if (occupancy >= 0.5) {
    return "#f97316";
  }
  return "#f59e0b";
}

function formatActionBadge(action: ControlActionType): {
  label: string;
  bg: string;
  stroke: string;
  text: string;
} {
  switch (action) {
    case "RED_TRUNCATION":
      return {
        label: "EARLY FLUSH",
        bg: "rgba(34, 211, 238, 0.16)",
        stroke: "#22d3ee",
        text: "#67e8f9",
      };
    case "GREEN_EXTENSION":
      return {
        label: "GREEN WAVE",
        bg: "rgba(16, 185, 129, 0.16)",
        stroke: "#10b981",
        text: "#6ee7b7",
      };
    case "UPSTREAM_METERING":
      return {
        label: "UPSTREAM METERING",
        bg: "rgba(245, 158, 11, 0.16)",
        stroke: "#f59e0b",
        text: "#fcd34d",
      };
    case "RECOVERY":
      return {
        label: "RECOVERY",
        bg: "rgba(168, 85, 247, 0.16)",
        stroke: "#a855f7",
        text: "#d8b4fe",
      };
    default:
      return {
        label: "HOLD",
        bg: "rgba(148, 163, 184, 0.12)",
        stroke: "#475569",
        text: "#cbd5e1",
      };
  }
}

function formatPulseCaption(pulse: ApiPulsePacket): string {
  const etaPart =
    pulse.eta_s !== null ? `ETA ${Math.round(pulse.eta_s)}s` : `RISK ${pulse.risk_index.toFixed(2)}`;
  if (pulse.type === "EV_SPILLBACK_ALERT") {
    return `API: EV ${etaPart} -> FLUSH ${pulse.to}`;
  }
  if (pulse.type === "SPILLBACK_METERING_BACKPRESSURE") {
    return `API: METER ${pulse.to} -> PROTECT ${pulse.from}`;
  }
  return `API: WAVE ${etaPart} -> ${pulse.to}`;
}

interface TrackRendererProps {
  title: string;
  subtitle: string;
  accentColor: string;
  roadY: number;
  states: Record<JunctionID, JunctionStatePacket>;
  proposals?: Record<JunctionID, ProposedControlAction>;
  apiPulses?: ApiPulsePacket[];
  evPositionM: number;
  evSpeedMps: number;
  evTrapped: boolean;
  evCompleted: boolean;
}

function RoadTrack({
  title,
  subtitle,
  accentColor,
  headerY,
  roadY,
  states,
  proposals,
  apiPulses,
  evPositionM,
  evSpeedMps,
  evTrapped,
  evCompleted,
}: TrackRendererProps & { headerY: number }) {
  const roadHeight = 46;
  const evSvgX = mapCorridorX(evPositionM);
  const speedKmh = Math.round(evSpeedMps * 3.6);

  return (
    <g>
      {/* Track header label positioned cleanly above badges and API arcs */}
      <text
        x={22}
        y={headerY}
        fill={accentColor}
        fontSize={12}
        fontWeight={700}
        letterSpacing="0.06em"
      >
        {title}
      </text>
      <text x={22} y={headerY + 14} fill="#94a3b8" fontSize={10}>
        {subtitle}
      </text>

      {/* Main asphalt roadway */}
      <rect
        x={SVG_ROAD_LEFT - 10}
        y={roadY}
        width={SVG_ROAD_WIDTH + 20}
        height={roadHeight}
        rx={8}
        fill="#0b1120"
        stroke="#1e293b"
        strokeWidth={1.5}
      />

      {/* Dashed road centerline */}
      <line
        x1={SVG_ROAD_LEFT}
        y1={roadY + roadHeight / 2}
        x2={SVG_ROAD_RIGHT}
        y2={roadY + roadHeight / 2}
        stroke="#334155"
        strokeWidth={1.5}
        strokeDasharray="10 10"
      />

      {/* Intersections J_A, J_B, J_C */}
      {JUNCTION_ORDER.map((jid) => {
        const jx = mapCorridorX(JUNCTION_COORDS[jid]);
        const pkt = states[jid];
        const queuePx = mapQueueWidth(pkt.queue_length_m);
        const occ = pkt.spatial_occupancy_ratio;
        const queueColor = getQueueColor(occ);
        const ewColor = getArterialSignalColor(pkt.active_phase);
        const nsColor = getCrossSignalColor(pkt.active_phase);
        const proposal = proposals?.[jid];
        const badge = proposal ? formatActionBadge(proposal.action_type) : null;

        return (
          <g key={jid}>
            {/* Cross-street asphalt */}
            <rect
              x={jx - 16}
              y={roadY - 16}
              width={32}
              height={roadHeight + 32}
              fill="#0b1120"
              stroke="#1e293b"
              strokeWidth={1}
            />

            {/* Stop line */}
            <line
              x1={jx - 16}
              y1={roadY + 3}
              x2={jx - 16}
              y2={roadY + roadHeight - 3}
              stroke="#cbd5e1"
              strokeWidth={2}
              strokeOpacity={0.7}
            />

            {/* Dynamic standing queue block extending backward from stop line */}
            <rect
              x={jx - 16 - queuePx}
              y={roadY + 8}
              width={Math.max(0, queuePx)}
              height={roadHeight - 16}
              rx={4}
              fill={queueColor}
              fillOpacity={occ >= 0.78 ? 0.85 : 0.72}
              className="transition-all duration-300 ease-linear"
            />
            {queuePx > 34 ? (
              <text
                x={jx - 16 - queuePx / 2}
                y={roadY + roadHeight / 2 + 4}
                textAnchor="middle"
                fill="#020617"
                fontSize={10}
                fontWeight={700}
                className="font-mono"
              >
                {Math.round(pkt.queue_length_m)}m
              </text>
            ) : null}

            {/* Dual signal head housing (EW Arterial + NS Cross-street) */}
            <rect
              x={jx + 18}
              y={roadY - 12}
              width={26}
              height={14}
              rx={4}
              fill="#020617"
              stroke="#334155"
              strokeWidth={1}
            />
            <circle cx={jx + 25} cy={roadY - 5} r={4} fill={ewColor} />
            <circle cx={jx + 37} cy={roadY - 5} r={4} fill={nsColor} />

            {/* Junction label below intersection */}
            <text
              x={jx}
              y={roadY + roadHeight + 16}
              textAnchor="middle"
              fill="#e2e8f0"
              fontSize={11}
              fontWeight={700}
              className="font-mono"
            >
              {jid} ({JUNCTION_COORDS[jid]}m)
            </text>

            {/* AegisFlow Action Mode Badge */}
            {badge ? (
              <g>
                <rect
                  x={jx - 62}
                  y={roadY - 40}
                  width={124}
                  height={18}
                  rx={9}
                  fill={badge.bg}
                  stroke={badge.stroke}
                  strokeWidth={1}
                />
                <text
                  x={jx}
                  y={roadY - 28}
                  textAnchor="middle"
                  fill={badge.text}
                  fontSize={9}
                  fontWeight={700}
                  className="font-mono"
                >
                  {badge.label}
                </text>
              </g>
            ) : null}
          </g>
        );
      })}

      {/* Inter-junction glowing API telemetry pulses (AegisFlow track) */}
      {apiPulses?.map((pulse, idx) => {
        const fromX = mapCorridorX(JUNCTION_COORDS[pulse.from]);
        const toX = mapCorridorX(JUNCTION_COORDS[pulse.to]);
        const midX = (fromX + toX) / 2;
        const arcOffset = idx % 2 === 0 ? -74 : -96;
        const pathD = `M ${fromX} ${roadY - 16} Q ${midX} ${roadY + arcOffset} ${toX} ${roadY - 16}`;
        const strokeColor =
          pulse.type === "SPILLBACK_METERING_BACKPRESSURE"
            ? "#f59e0b"
            : "#22d3ee";

        return (
          <g key={`${pulse.from}-${pulse.to}-${pulse.type}`}>
            <path
              d={pathD}
              fill="none"
              stroke={strokeColor}
              strokeWidth={2}
              strokeDasharray="6 6"
              className="animate-api-dash"
            />
            <circle r={4.5} fill={strokeColor}>
              <animateMotion dur="1.2s" repeatCount="indefinite" path={pathD} />
            </circle>
            <rect
              x={midX - 88}
              y={roadY + arcOffset - 8}
              width={176}
              height={17}
              rx={8}
              fill="#020617"
              fillOpacity={0.92}
              stroke={strokeColor}
              strokeWidth={1}
            />
            <text
              x={midX}
              y={roadY + arcOffset + 4}
              textAnchor="middle"
              fill={strokeColor}
              fontSize={9}
              fontWeight={700}
              className="font-mono"
            >
              {formatPulseCaption(pulse)}
            </text>
          </g>
        );
      })}

      {/* Animated Ambulance Group */}
      <g
        style={{ transform: `translateX(${evSvgX}px)` }}
        className="transition-all duration-300 ease-linear"
      >
        {/* Trapped in spillback pulsing alert */}
        {evTrapped ? (
          <g>
            <rect
              x={-72}
              y={roadY - 26}
              width={144}
              height={18}
              rx={9}
              fill="#e11d48"
              stroke="#fda4af"
              strokeWidth={1.2}
              className="animate-pulse"
            />
            <text
              x={0}
              y={roadY - 14}
              textAnchor="middle"
              fill="#ffffff"
              fontSize={9.5}
              fontWeight={800}
              className="font-mono"
            >
              TRAPPED IN SPILLBACK
            </text>
          </g>
        ) : null}

        {/* Ambulance body */}
        <rect
          x={-17}
          y={roadY + 12}
          width={34}
          height={22}
          rx={5}
          fill={evCompleted ? "#10b981" : "#f8fafc"}
          stroke={evTrapped ? "#f43f5e" : "#22d3ee"}
          strokeWidth={2}
        />
        {/* Medical cross */}
        <rect x={-7} y={roadY + 19} width={8} height={3} fill="#e11d48" />
        <rect x={-4.5} y={roadY + 16.5} width={3} height={8} fill="#e11d48" />
        {/* Flashing beacon */}
        <circle
          cx={10}
          cy={roadY + 23}
          r={3.5}
          fill={evTrapped ? "#f43f5e" : "#22d3ee"}
          className="animate-ping"
        />
        <circle
          cx={10}
          cy={roadY + 23}
          r={2.5}
          fill={evTrapped ? "#fb7185" : "#67e8f9"}
        />

        {/* Live telemetry pill beneath ambulance */}
        <rect
          x={-44}
          y={roadY + roadHeight + 23}
          width={88}
          height={16}
          rx={4}
          fill="#0f172a"
          stroke="#334155"
          strokeWidth={1}
        />
        <text
          x={0}
          y={roadY + roadHeight + 34}
          textAnchor="middle"
          fill={evTrapped ? "#fda4af" : "#67e8f9"}
          fontSize={9}
          fontWeight={700}
          className="font-mono"
        >
          {evCompleted ? "CLEARED" : `${speedKmh} km/h · ${Math.round(evPositionM)}m`}
        </text>
      </g>
    </g>
  );
}

export function CorridorRaceCanvas({ frame }: CorridorRaceCanvasProps) {
  if (frame === null) {
    return (
      <section className="flex h-full min-h-0 flex-col items-center justify-center rounded-xl border border-slate-800 bg-slate-900/70 p-4 text-center">
        <p className="font-mono text-sm text-slate-400">
          Waiting for corridor WebSocket frame from AegisFlow Gateway...
        </p>
      </section>
    );
  }

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-950/90 p-2.5 shadow-[0_0_30px_rgba(34,211,238,0.06)]">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">
            Dual-Track Corridor Race (900m Arterial Digital Twin)
          </h2>
          <p className="text-xs text-slate-400">
            Identical vehicle demand &amp; initial queues — isolated reactive EVP
            vs. predictive spillback-aware coordination
          </p>
        </div>
        <div className="flex items-center gap-4 font-mono text-xs text-slate-300">
          <span className="rounded border border-slate-800 bg-slate-900 px-2.5 py-1">
            TICK: <strong className="text-cyan-300">{frame.tick}s</strong>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-amber-500" />
            Queue &lt; 50%
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-rose-500" />
            Spillback (&ge;78%)
          </span>
        </div>
      </div>

      <div className="min-h-0 w-full flex-1 overflow-hidden">
        <svg
          viewBox="0 0 1120 448"
          className="h-full min-w-0 w-full select-none"
          role="img"
          aria-label="Dual-track emergency corridor comparison canvas"
        >
          <rect width="1120" height="448" rx="10" fill="#020617" />

          {/* Track 1: Baseline EVP */}
          <RoadTrack
            title="TRACK A — CONVENTIONAL ISOLATED EVP (BASELINE)"
            subtitle="Local preemption <= 110m only · Blind to J_B standing queues"
            accentColor="#fb7185"
            headerY={22}
            roadY={78}
            states={frame.baseline.states}
            evPositionM={frame.baseline.ev_position_m}
            evSpeedMps={frame.baseline.ev_speed_mps}
            evTrapped={frame.baseline.ev_trapped_in_spillback}
            evCompleted={frame.baseline.kpis.ev_completed}
          />

          {/* Track divider */}
          <line
            x1={22}
            y1={178}
            x2={1098}
            y2={178}
            stroke="#1e293b"
            strokeWidth={1}
            strokeDasharray="4 4"
          />

          {/* Track 2: AegisFlow v2.0 */}
          <RoadTrack
            title="TRACK B — AEGISFLOW v2.0 (PREDICTIVE CORRIDOR ORCHESTRATION)"
            subtitle="45s physics-informed spillback predictor · Inter-junction API coordination · Deterministic Safety Shield"
            accentColor="#22d3ee"
            headerY={200}
            roadY={336}
            states={frame.aegisflow.states}
            proposals={frame.aegisflow.proposals}
            apiPulses={frame.aegisflow.active_api_packets}
            evPositionM={frame.aegisflow.ev_position_m}
            evSpeedMps={frame.aegisflow.ev_speed_mps}
            evTrapped={frame.aegisflow.ev_trapped_in_spillback}
            evCompleted={frame.aegisflow.kpis.ev_completed}
          />
        </svg>
      </div>
    </section>
  );
}
