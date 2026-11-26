import type { GatewayConnectionState } from "../types/gateway";

interface GatewayStatusBadgeProps {
  state: GatewayConnectionState;
  service?: string;
}

const BADGE_STYLES: Record<
  GatewayConnectionState,
  { container: string; dot: string; label: string }
> = {
  connected: {
    container:
      "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
    dot: "bg-emerald-400",
    label: "AegisFlow Command Center — Gateway Connected",
  },
  checking: {
    container: "border-amber-500/30 bg-amber-500/10 text-amber-300",
    dot: "bg-amber-400 animate-pulse",
    label: "AegisFlow Command Center — Checking Gateway...",
  },
  disconnected: {
    container: "border-rose-500/30 bg-rose-500/10 text-rose-300",
    dot: "bg-rose-400",
    label: "AegisFlow Command Center — Gateway Disconnected",
  },
};

export function GatewayStatusBadge({
  state,
  service,
}: GatewayStatusBadgeProps) {
  const style = BADGE_STYLES[state];

  return (
    <div
      role="status"
      aria-live="polite"
      className={`inline-flex items-center gap-2.5 rounded-full border px-4 py-1.5 text-sm font-medium ${style.container}`}
    >
      <span className={`h-2.5 w-2.5 rounded-full ${style.dot}`} />
      <span>{style.label}</span>
      {service ? (
        <span className="rounded bg-slate-900/70 px-2 py-0.5 font-mono text-xs text-slate-300">
          {service}
        </span>
      ) : null}
    </div>
  );
}
