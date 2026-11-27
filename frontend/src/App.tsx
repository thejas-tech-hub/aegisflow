import { useState } from "react";
import {
  BarChart3,
  Box,
  Map as MapIcon,
  Pause,
  Play,
  RotateCcw,
  Siren,
  SkipForward,
} from "lucide-react";
import { BenchmarkModal } from "./components/BenchmarkModal";
import { Corridor3DTwin } from "./components/Corridor3DTwin";
import { CorridorRaceCanvas } from "./components/CorridorRaceCanvas";
import { KpiStrip } from "./components/KpiStrip";
import { LiveAnalyticsDock } from "./components/LiveAnalyticsDock";
import { LiveCorridorInsights } from "./components/LiveCorridorInsights";
import {
  AnalyticsView,
  CorridorDetailView,
  HelpWalkthroughView,
} from "./components/SecondaryViews";
import { Sidebar, type NavTabId } from "./components/Sidebar";
import { VisionBevPanel } from "./components/VisionBevPanel";
import { useCorridorSocket } from "./hooks/useCorridorSocket";
import type {
  ScenarioPreset,
  SocketConnectionStatus,
  SpeedMultiplier,
} from "./types/telemetry";

const SCENARIO_OPTIONS: readonly { value: ScenarioPreset; label: string }[] = [
  { value: "peak_spillback", label: "Peak Spillback" },
  { value: "moderate_mixed", label: "Moderate Mixed" },
  { value: "severe_gridlock", label: "Severe Gridlock" },
];

const SPEED_OPTIONS: readonly SpeedMultiplier[] = [1, 2, 4];

const STATUS_PILL: Record<
  SocketConnectionStatus,
  { wrap: string; dot: string; text: string }
> = {
  connected: {
    wrap: "border-emerald-500/45 bg-emerald-500/15 text-emerald-300",
    dot: "bg-emerald-400",
    text: "WS Connected",
  },
  reconnecting: {
    wrap: "border-amber-500/45 bg-amber-500/15 text-amber-300",
    dot: "bg-amber-400 animate-pulse",
    text: "WS Reconnecting",
  },
  offline: {
    wrap: "border-rose-500/45 bg-rose-500/15 text-rose-300",
    dot: "bg-rose-400",
    text: "WS Offline",
  },
};

export function App() {
  const {
    latestFrame,
    chartHistory,
    shieldEvents,
    connectionStatus,
    isRunning,
    scenario,
    speedMultiplier,
    actionError,
    start,
    pause,
    reset,
    step,
    setScenario,
    setSpeed,
    injectEv,
    runBenchmark,
  } = useCorridorSocket();

  const [activeTab, setActiveTab] = useState<NavTabId>("dashboard");
  const [heroViewMode, setHeroViewMode] = useState<"3d" | "2d">("3d");
  const [benchmarkOpen, setBenchmarkOpen] = useState<boolean>(false);

  const aegisKpis = latestFrame?.aegisflow.kpis;
  const statusStyle = STATUS_PILL[connectionStatus];

  return (
    <div className="ambient-cockpit-bg flex min-h-screen text-slate-100">
      {/* Left Navigation Sidebar Rail */}
      <Sidebar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        isConnected={connectionStatus === "connected"}
      />

      {/* Main Cockpit Column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top Command Bar */}
        <header className="glass-card sticky top-0 z-30 border-b border-slate-800/80">
          <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-3 px-4 py-2.5 sm:px-5">
            {/* Title + WS Pill */}
            <div className="flex items-center gap-3">
              <div>
                <div className="flex items-center gap-2.5">
                  <h1 className="font-display text-base font-bold tracking-tight text-slate-100">
                    AegisFlow <span className="text-cyan-300">v2.0</span>
                  </h1>
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-sans text-[11px] font-medium ${statusStyle.wrap}`}
                  >
                    <span className={`h-2 w-2 rounded-full ${statusStyle.dot}`} />
                    {statusStyle.text}
                  </span>
                </div>
                <p className="font-sans text-[11px] text-slate-400">
                  Predictive Emergency Corridor Command Center
                </p>
              </div>
            </div>

            {/* Playback & Scenario Controls + TJ Avatar */}
            <div className="flex flex-wrap items-center gap-2">
              <select
                aria-label="Corridor scenario"
                value={scenario}
                onChange={(e) => void setScenario(e.target.value as ScenarioPreset)}
                className="rounded-lg border border-slate-700/90 bg-slate-900/90 px-3 py-1.5 text-xs font-medium text-slate-200 focus:border-cyan-400 focus:outline-none"
              >
                {SCENARIO_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>

              <div className="inline-flex items-center rounded-lg border border-slate-700/90 bg-slate-900/90 p-0.5">
                {isRunning ? (
                  <button
                    type="button"
                    onClick={() => void pause()}
                    className="inline-flex items-center gap-1.5 rounded-md bg-amber-500/20 px-2.5 py-1 text-xs font-semibold text-amber-300 hover:bg-amber-500/30"
                  >
                    <Pause className="h-3.5 w-3.5" />
                    Pause
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => void start()}
                    className="inline-flex items-center gap-1.5 rounded-md bg-emerald-500/20 px-2.5 py-1 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/30"
                  >
                    <Play className="h-3.5 w-3.5" />
                    Play
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => void step()}
                  disabled={isRunning}
                  className="inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                  title="Advance one tick"
                >
                  <SkipForward className="h-3.5 w-3.5" />
                  Step
                </button>
                <button
                  type="button"
                  onClick={() => void reset()}
                  className="inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium text-slate-300 hover:bg-slate-800"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Reset
                </button>
              </div>

              <div className="inline-flex items-center rounded-lg border border-slate-700/90 bg-slate-900/90 p-0.5 font-mono text-xs">
                {SPEED_OPTIONS.map((spd) => (
                  <button
                    key={spd}
                    type="button"
                    onClick={() => void setSpeed(spd)}
                    className={`rounded-md px-2.5 py-1 font-semibold transition-all ${
                      speedMultiplier === spd
                        ? "bg-cyan-500/25 text-cyan-200 shadow-[0_0_12px_rgba(34,211,238,0.25)] ring-1 ring-cyan-400/50"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    {spd}x
                  </button>
                ))}
              </div>

              <button
                type="button"
                onClick={() => void injectEv()}
                className="inline-flex items-center gap-1.5 rounded-lg border border-rose-400/65 bg-rose-600/90 px-3 py-1.5 text-xs font-bold text-white shadow-[0_0_18px_rgba(244,63,94,0.4)] hover:bg-rose-500"
              >
                <Siren className="h-3.5 w-3.5" />
                Dispatch EV
              </button>

              <button
                type="button"
                onClick={() => setBenchmarkOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-500/45 bg-cyan-500/15 px-3 py-1.5 text-xs font-semibold text-cyan-200 shadow-[0_0_14px_rgba(34,211,238,0.16)] hover:bg-cyan-500/25"
              >
                <BarChart3 className="h-3.5 w-3.5" />
                Run Full A/B Benchmark
              </button>

              {/* Glowing TJ Avatar Badge */}
              <div
                className="flex h-8 w-8 items-center justify-center rounded-full border border-cyan-400/60 bg-gradient-to-br from-cyan-500/30 to-indigo-500/30 font-display text-xs font-bold text-cyan-200 shadow-[0_0_14px_rgba(34,211,238,0.3)]"
                title="Thejas J — Lead Architect"
              >
                TJ
              </div>
            </div>
          </div>
        </header>

        {/* Main Workspace Body */}
        <main
          className={`mx-auto w-full max-w-[1600px] flex-1 ${
            activeTab === "dashboard"
              ? "space-y-2 px-4 py-2 sm:px-5"
              : "space-y-4 px-4 py-4 sm:px-5"
          }`}
        >
          {actionError ? (
            <div className="glass-card-crimson rounded-lg border px-4 py-2 font-mono text-xs text-rose-300">
              Gateway notice: {actionError}
            </div>
          ) : null}

          {activeTab === "dashboard" ? (
            <>
              {/* Top 4 KPI Sparkline Cards */}
              <KpiStrip latestFrame={latestFrame} chartHistory={chartHistory} />

              {/* Main Cockpit Row: 8-Col 3D Digital Twin + 4-Col Live Corridor Insights */}
              <section className="grid grid-cols-1 gap-4 xl:h-[340px] xl:grid-cols-12">
                <div className="glass-card-cyan flex flex-col gap-2 rounded-xl border p-2.5 xl:col-span-8 xl:min-h-0">
                  <div className="flex flex-wrap items-center justify-between gap-2 px-1">
                    <div>
                      <h2 className="font-sans text-sm font-semibold tracking-tight text-slate-100">
                        Corridor Digital Twin Viewport
                      </h2>
                      <p className="font-sans text-[11px] text-slate-400">
                        Real-time Three.js 3D telemetry &amp; 2D schematic race view
                      </p>
                    </div>

                    <div
                      role="tablist"
                      aria-label="Corridor viewport mode"
                      className="inline-flex items-center rounded-lg border border-slate-700/80 bg-slate-950/90 p-0.5 font-sans text-[11px]"
                    >
                      <button
                        type="button"
                        role="tab"
                        aria-selected={heroViewMode === "3d"}
                        onClick={() => setHeroViewMode("3d")}
                        className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 font-semibold transition-colors ${
                          heroViewMode === "3d"
                            ? "bg-cyan-500/20 text-cyan-200 ring-1 ring-cyan-400/50"
                            : "text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        <Box className="h-3.5 w-3.5" />
                        3D Digital Twin
                      </button>
                      <button
                        type="button"
                        role="tab"
                        aria-selected={heroViewMode === "2d"}
                        onClick={() => setHeroViewMode("2d")}
                        className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 font-semibold transition-colors ${
                          heroViewMode === "2d"
                            ? "bg-cyan-500/20 text-cyan-200 ring-1 ring-cyan-400/50"
                            : "text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        <MapIcon className="h-3.5 w-3.5" />
                        2D Schematic
                      </button>
                    </div>
                  </div>

                  {heroViewMode === "3d" ? (
                    <Corridor3DTwin frame={latestFrame} />
                  ) : (
                    <CorridorRaceCanvas frame={latestFrame} />
                  )}
                </div>

                <div className="xl:col-span-4 xl:min-h-0">
                  <LiveCorridorInsights
                    frame={latestFrame}
                    chartHistory={chartHistory}
                  />
                </div>
              </section>

              {/* Bottom Equal-Height Row (h-[320px] each) */}
              <LiveAnalyticsDock
                chartHistory={chartHistory}
                shieldEvents={shieldEvents}
                auditSummary={aegisKpis?.shield_audit_summary ?? null}
              />
            </>
          ) : null}

          {activeTab === "vision" ? (
            <VisionBevPanel
              onTriggeredCorridor={() => setActiveTab("dashboard")}
            />
          ) : null}

          {activeTab === "corridor" ? (
            <CorridorDetailView frame={latestFrame} />
          ) : null}

          {activeTab === "analytics" ? (
            <AnalyticsView scenario={scenario} runBenchmark={runBenchmark} />
          ) : null}

          {activeTab === "help" ? <HelpWalkthroughView /> : null}
        </main>
      </div>

      <BenchmarkModal
        isOpen={benchmarkOpen}
        scenario={scenario}
        onClose={() => setBenchmarkOpen(false)}
        runBenchmark={runBenchmark}
      />
    </div>
  );
}

export default App;
