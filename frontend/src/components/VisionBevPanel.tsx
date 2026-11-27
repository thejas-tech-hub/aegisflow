import { useCallback, useEffect, useMemo, useState } from "react";
import { Camera, Pause, Play, Radio, Siren } from "lucide-react";
import type { JunctionStatePacket } from "../types/telemetry";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

interface VisionSnapshotResponse {
  frame_jpeg_b64: string;
  packet: JunctionStatePacket;
  ev_triggered: boolean;
}

interface VisionBevPanelProps {
  onTriggeredCorridor: () => void;
}

function isVisionSnapshotResponse(
  payload: unknown,
): payload is VisionSnapshotResponse {
  if (typeof payload !== "object" || payload === null) {
    return false;
  }
  const rec = payload as Record<string, unknown>;
  return (
    typeof rec.frame_jpeg_b64 === "string" &&
    typeof rec.ev_triggered === "boolean" &&
    typeof rec.packet === "object" &&
    rec.packet !== null
  );
}

function SyntaxHighlightedJson({ packet }: { packet: JunctionStatePacket }) {
  const lines = useMemo(() => {
    const raw = JSON.stringify(packet, null, 2);
    return raw.split("\n");
  }, [packet]);

  return (
    <pre className="max-h-[300px] overflow-auto rounded-lg border border-slate-800/90 bg-slate-950/90 p-3 font-mono text-[11px] leading-relaxed">
      {lines.map((line, idx) => {
        const keyMatch = /^(\s*)"([^"]+)":\s*(.*)$/.exec(line);
        if (!keyMatch) {
          return (
            <div key={idx} className="text-slate-400">
              {line}
            </div>
          );
        }
        const [, indent, key, rest] = keyMatch;
        const isBoolOrNull =
          rest.startsWith("true") ||
          rest.startsWith("false") ||
          rest.startsWith("null");
        const isString = rest.startsWith('"');
        const valClass = isString
          ? "text-emerald-300"
          : isBoolOrNull
            ? "text-amber-300"
            : "text-cyan-300";

        return (
          <div key={idx}>
            <span className="text-slate-500">{indent}</span>
            <span className="text-indigo-300">"{key}"</span>
            <span className="text-slate-400">: </span>
            <span className={valClass}>{rest}</span>
          </div>
        );
      })}
    </pre>
  );
}

export function VisionBevPanel({ onTriggeredCorridor }: VisionBevPanelProps) {
  const [isLive, setIsLive] = useState<boolean>(true);
  const [snapshot, setSnapshot] = useState<VisionSnapshotResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isTriggering, setIsTriggering] = useState<boolean>(false);

  const fetchSnapshot = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/perception/snapshot`, {
        method: "GET",
        signal,
      });
      if (!response.ok) {
        throw new Error(`Perception endpoint returned HTTP ${response.status}`);
      }
      const data: unknown = await response.json();
      if (!isVisionSnapshotResponse(data)) {
        throw new Error("Invalid perception snapshot payload");
      }
      setSnapshot(data);
      setError(null);
    } catch (err: unknown) {
      if (signal?.aborted) {
        return;
      }
      setError(
        err instanceof Error ? err.message : "Failed to fetch CCTV snapshot",
      );
    }
  }, []);

  useEffect(() => {
    if (!isLive) {
      return;
    }
    const controller = new AbortController();
    void fetchSnapshot(controller.signal);

    const intervalId = window.setInterval(() => {
      void fetchSnapshot(controller.signal);
    }, 500);

    return () => {
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, [isLive, fetchSnapshot]);

  const handleTriggerCorridor = async (): Promise<void> => {
    setIsTriggering(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/perception/trigger-corridor`,
        { method: "POST" },
      );
      if (!response.ok) {
        throw new Error(`Trigger failed with HTTP ${response.status}`);
      }
      onTriggeredCorridor();
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to trigger 3D corridor",
      );
    } finally {
      setIsTriggering(false);
    }
  };

  const packet = snapshot?.packet ?? null;
  const payloadBytes = useMemo(() => {
    if (!packet) {
      return 0;
    }
    return new Blob([JSON.stringify(packet)]).size;
  }, [packet]);

  const sorPct = packet
    ? (packet.spatial_occupancy_ratio * 100).toFixed(1)
    : "0.0";
  const evConfPct = packet ? (packet.ev_confidence * 100).toFixed(0) : "0";

  return (
    <div className="space-y-4">
      {/* Top Control Bar */}
      <div className="glass-card-cyan flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-cyan-400/40 bg-cyan-500/15 text-cyan-300">
            <Camera className="h-4 w-4" />
          </div>
          <div>
            <h2 className="font-display text-sm font-bold tracking-tight text-slate-100">
              Roadside CCTV + BEV Spatial Occupancy Radar
            </h2>
            <p className="font-sans text-[11px] text-slate-400">
              YOLOv11n + ByteTrack homography projection streaming structured J_A
              packets
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={() => setIsLive((prev) => !prev)}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 font-sans text-xs font-semibold transition-all ${
              isLive
                ? "border-amber-400/50 bg-amber-500/20 text-amber-200 hover:bg-amber-500/30"
                : "border-emerald-400/50 bg-emerald-500/20 text-emerald-200 hover:bg-emerald-500/30"
            }`}
          >
            {isLive ? (
              <>
                <Pause className="h-3.5 w-3.5" />
                Pause Live Feed
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5" />
                Start Live Feed
              </>
            )}
          </button>

          <button
            type="button"
            disabled={isTriggering}
            onClick={() => void handleTriggerCorridor()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-rose-400/70 bg-rose-600/90 px-3.5 py-1.5 font-sans text-xs font-bold text-white shadow-[0_0_22px_rgba(244,63,94,0.55)] transition-all hover:bg-rose-500 disabled:opacity-50"
          >
            <Siren className="h-3.5 w-3.5 animate-pulse" />
            {isTriggering
              ? "Dispatching..."
              : "Trigger 3D Corridor from CCTV EV"}
          </button>
        </div>
      </div>

      {error ? (
        <div className="glass-card-crimson rounded-lg border px-4 py-2 font-mono text-xs text-rose-300">
          Vision bridge error: {error}
        </div>
      ) : null}

      {/* Main 8-col / 4-col Split */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        {/* Left (8 cols): Live Side-by-Side CCTV + BEV Viewport */}
        <section className="glass-card-cyan flex flex-col gap-3 rounded-xl border p-3.5 xl:col-span-8">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 font-mono text-xs text-slate-300">
              <Radio
                className={`h-3.5 w-3.5 ${
                  isLive ? "text-emerald-400 animate-pulse" : "text-slate-500"
                }`}
              />
              <span>JUNCTION J_A · 500ms POLL</span>
            </div>

            <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
              <span className="rounded-md border border-cyan-500/40 bg-cyan-500/15 px-2.5 py-1 text-cyan-200">
                SOR: {sorPct}%
              </span>
              <span className="rounded-md border border-indigo-500/40 bg-indigo-500/15 px-2.5 py-1 text-indigo-200">
                PCU: {packet ? packet.pcu_density.toFixed(1) : "0.0"}
              </span>
              <span
                className={`rounded-md border px-2.5 py-1 ${
                  snapshot?.ev_triggered
                    ? "border-rose-400/60 bg-rose-500/20 text-rose-200 shadow-[0_0_12px_rgba(244,63,94,0.35)]"
                    : "border-slate-700 bg-slate-900/80 text-slate-400"
                }`}
              >
                EV Conf: {evConfPct}%
              </span>
            </div>
          </div>

          <div className="relative flex min-h-[380px] items-center justify-center overflow-hidden rounded-lg border border-slate-800/90 bg-slate-950/90">
            {snapshot ? (
              <img
                src={`data:image/jpeg;base64,${snapshot.frame_jpeg_b64}`}
                alt="Roadside CCTV and Top-Down BEV Spatial Occupancy Radar"
                className="h-auto w-full object-contain"
              />
            ) : (
              <div className="font-mono text-xs text-slate-400">
                Connecting to roadside perception stream...
              </div>
            )}
          </div>
        </section>

        {/* Right (4 cols): Compact JunctionStatePacket Inspector + Vehicle Mix */}
        <section className="glass-card flex flex-col gap-3 rounded-xl border border-slate-800/80 p-3.5 xl:col-span-4">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h3 className="font-display text-sm font-semibold text-slate-100">
                Inter-Junction Payload
              </h3>
              <p className="font-sans text-[11px] text-slate-400">
                Structured JSON transmitted instead of raw CCTV video
              </p>
            </div>
            <span className="rounded-full border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-emerald-300">
              {payloadBytes > 0 ? `${payloadBytes} B` : "~1.2 KB"}
            </span>
          </div>

          {packet ? (
            <SyntaxHighlightedJson packet={packet} />
          ) : (
            <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-4 font-mono text-xs text-slate-500">
              Awaiting first JunctionStatePacket...
            </div>
          )}

          <div className="rounded-lg border border-slate-800/80 bg-slate-950/70 p-3">
            <h4 className="mb-2 font-sans text-xs font-semibold uppercase tracking-wider text-slate-400">
              Vehicle Mix Breakdown
            </h4>
            <div className="grid grid-cols-2 gap-2 font-mono text-xs">
              <div className="flex items-center justify-between rounded bg-slate-900/90 px-2.5 py-1.5">
                <span className="text-slate-400">2-Wheelers</span>
                <span className="font-semibold text-cyan-300">
                  {packet?.vehicle_mix.motorcycles ?? 0}
                </span>
              </div>
              <div className="flex items-center justify-between rounded bg-slate-900/90 px-2.5 py-1.5">
                <span className="text-slate-400">Autos</span>
                <span className="font-semibold text-amber-300">
                  {packet?.vehicle_mix.auto_rickshaws ?? 0}
                </span>
              </div>
              <div className="flex items-center justify-between rounded bg-slate-900/90 px-2.5 py-1.5">
                <span className="text-slate-400">Cars</span>
                <span className="font-semibold text-indigo-300">
                  {packet?.vehicle_mix.cars ?? 0}
                </span>
              </div>
              <div className="flex items-center justify-between rounded bg-slate-900/90 px-2.5 py-1.5">
                <span className="text-slate-400">Buses/Trucks</span>
                <span className="font-semibold text-purple-300">
                  {packet?.vehicle_mix.buses_trucks ?? 0}
                </span>
              </div>
              <div className="col-span-2 flex items-center justify-between rounded border border-rose-500/30 bg-rose-500/10 px-2.5 py-1.5">
                <span className="text-rose-200">Emergency Vehicles</span>
                <span className="font-bold text-rose-300">
                  {packet?.vehicle_mix.emergency_vehicles ?? 0}
                </span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
