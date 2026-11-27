import {
  BarChart3,
  Eye,
  GitFork,
  HelpCircle,
  Home,
} from "lucide-react";

export type NavTabId =
  | "dashboard"
  | "vision"
  | "analytics"
  | "corridor"
  | "help";

interface SidebarProps {
  activeTab: NavTabId;
  onSelectTab: (tab: NavTabId) => void;
  isConnected: boolean;
}

const NAV_ITEMS: readonly {
  id: NavTabId;
  label: string;
  icon: typeof Home;
}[] = [
  { id: "dashboard", label: "Dashboard", icon: Home },
  { id: "vision", label: "Vision", icon: Eye },
  { id: "analytics", label: "Analytics", icon: BarChart3 },
  { id: "corridor", label: "Corridor", icon: GitFork },
  { id: "help", label: "Help", icon: HelpCircle },
];

export function Sidebar({
  activeTab,
  onSelectTab,
  isConnected,
}: SidebarProps) {
  return (
    <aside
      aria-label="Primary navigation"
      className="glass-card sticky top-0 z-40 flex h-screen w-20 shrink-0 flex-col items-center justify-between border-r border-slate-800/80 py-4"
    >
      {/* Top AF Glowing Emblem */}
      <div className="flex flex-col items-center gap-6">
        <button
          type="button"
          onClick={() => onSelectTab("dashboard")}
          className="flex h-11 w-11 items-center justify-center rounded-xl border border-cyan-400/50 bg-cyan-500/15 font-display text-base font-bold tracking-tight text-cyan-300 shadow-[0_0_20px_rgba(34,211,238,0.3)] transition-transform hover:scale-105"
          title="AegisFlow Command Center"
        >
          AF
        </button>

        {/* Navigation Tabs */}
        <nav className="flex flex-col items-center gap-2.5">
          {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
            const isActive = activeTab === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => onSelectTab(id)}
                className={`group relative flex w-16 flex-col items-center gap-1 rounded-xl px-1.5 py-2.5 text-[10px] font-medium transition-all ${
                  isActive
                    ? "border border-cyan-400/45 bg-cyan-500/15 text-cyan-200 shadow-[0_0_18px_rgba(34,211,238,0.22)]"
                    : "border border-transparent text-slate-400 hover:border-slate-700/70 hover:bg-slate-900/70 hover:text-slate-200"
                }`}
              >
                {isActive ? (
                  <span className="absolute -left-2 top-2.5 bottom-2.5 w-1 rounded-r-full bg-cyan-400 shadow-[0_0_10px_#22d3ee]" />
                ) : null}
                <Icon
                  className={`h-4 w-4 ${
                    isActive
                      ? "text-cyan-300 drop-shadow-[0_0_6px_rgba(34,211,238,0.8)]"
                      : "text-slate-400 group-hover:text-slate-200"
                  }`}
                />
                <span>{label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Bottom Live System Operational Indicator */}
      <div className="flex flex-col items-center gap-1.5 px-2 text-center">
        <svg
          viewBox="0 0 48 16"
          className="h-4 w-12"
          aria-hidden="true"
        >
          <polyline
            fill="none"
            stroke={isConnected ? "#22d3ee" : "#f59e0b"}
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            points="1,10 10,10 14,4 19,14 24,2 29,12 33,10 47,10"
            className="animate-heartbeat"
          />
        </svg>
        <div className="flex items-center gap-1 font-sans text-[9px] font-medium leading-tight text-emerald-300">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              isConnected ? "bg-emerald-400 animate-pulse" : "bg-amber-400"
            }`}
          />
          <span>{isConnected ? "System OK" : "Syncing"}</span>
        </div>
      </div>
    </aside>
  );
}
