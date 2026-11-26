import { GatewayStatusBadge } from "./components/GatewayStatusBadge";
import { useGatewayHealth } from "./hooks/useGatewayHealth";

export function App() {
  const { state, health, error } = useGatewayHealth();

  return (
    <div className="min-h-screen bg-command-bg text-slate-100">
      <header className="border-b border-command-border bg-command-surface/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-500/15 text-sm font-bold text-cyan-400 ring-1 ring-cyan-500/30">
              AF
            </div>
            <div>
              <h1 className="text-base font-semibold tracking-tight text-slate-100">
                AegisFlow
              </h1>
              <p className="text-xs text-slate-400">
                Traffic Operations Command Center
              </p>
            </div>
          </div>

          <GatewayStatusBadge state={state} service={health?.service} />
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        <section className="rounded-xl border border-command-border bg-command-surface p-6">
          <h2 className="text-sm font-medium uppercase tracking-wider text-slate-400">
            Gateway Telemetry Status
          </h2>
          <p className="mt-2 text-sm text-slate-300">
            {state === "connected" && health
              ? `Connected to ${health.service} (status: ${health.status}).`
              : state === "checking"
                ? "Verifying connection to FastAPI gateway..."
                : `Unable to reach FastAPI gateway${error ? `: ${error}` : "."}`}
          </p>
        </section>
      </main>
    </div>
  );
}

export default App;
