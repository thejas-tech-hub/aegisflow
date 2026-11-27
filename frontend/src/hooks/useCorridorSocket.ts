import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ABFrameSnapshot,
  BenchmarkSummary,
  ChartHistoryPoint,
  JunctionID,
  ScenarioPreset,
  ShieldEventEntry,
  SimControlRequest,
  SimControlResponse,
  SocketConnectionStatus,
  SpeedMultiplier,
} from "../types/telemetry";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const WS_URL =
  import.meta.env.VITE_WS_URL ?? "ws://127.0.0.1:8000/ws/corridor";

const MAX_CHART_HISTORY = 120;
const MAX_SHIELD_EVENTS = 100;
const JUNCTIONS: readonly JunctionID[] = ["J_A", "J_B", "J_C"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isABFrameSnapshot(value: unknown): value is ABFrameSnapshot {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.tick === "number" &&
    typeof value.scenario === "string" &&
    isRecord(value.baseline) &&
    isRecord(value.aegisflow) &&
    isRecord(value.comparison_kpis)
  );
}

export interface UseCorridorSocketResult {
  latestFrame: ABFrameSnapshot | null;
  chartHistory: ChartHistoryPoint[];
  shieldEvents: ShieldEventEntry[];
  connectionStatus: SocketConnectionStatus;
  isRunning: boolean;
  scenario: ScenarioPreset;
  speedMultiplier: SpeedMultiplier;
  evInjectedAtJa: boolean;
  actionError: string | null;
  start: () => Promise<void>;
  pause: () => Promise<void>;
  reset: () => Promise<void>;
  step: () => Promise<void>;
  setScenario: (nextScenario: ScenarioPreset) => Promise<void>;
  setSpeed: (nextSpeed: SpeedMultiplier) => Promise<void>;
  injectEv: () => Promise<void>;
  runBenchmark: (targetScenario?: ScenarioPreset) => Promise<BenchmarkSummary>;
}

export function useCorridorSocket(): UseCorridorSocketResult {
  const [latestFrame, setLatestFrame] = useState<ABFrameSnapshot | null>(null);
  const [chartHistory, setChartHistory] = useState<ChartHistoryPoint[]>([]);
  const [shieldEvents, setShieldEvents] = useState<ShieldEventEntry[]>([]);
  const [connectionStatus, setConnectionStatus] =
    useState<SocketConnectionStatus>("reconnecting");
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [scenario, setScenarioState] =
    useState<ScenarioPreset>("peak_spillback");
  const [speedMultiplier, setSpeedMultiplier] = useState<SpeedMultiplier>(1);
  const [evInjectedAtJa, setEvInjectedAtJa] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const lastPhasesRef = useRef<Partial<Record<JunctionID, string>>>({});
  const pendingStepRef = useRef<boolean>(false);
  const restoreSpeedRef = useRef<SpeedMultiplier | null>(null);

  const postSimControl = useCallback(
    async (payload: SimControlRequest): Promise<SimControlResponse> => {
      const response = await fetch(`${API_BASE_URL}/api/v1/sim/control`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`Control HTTP ${response.status}: ${text}`);
      }
      const data: unknown = await response.json();
      if (!isRecord(data) || typeof data.is_running !== "boolean") {
        throw new Error("Invalid SimControlResponse payload from gateway");
      }
      const typed = data as unknown as SimControlResponse;
      setIsRunning(typed.is_running);
      setScenarioState(typed.scenario);
      setSpeedMultiplier(typed.speed_multiplier);
      setEvInjectedAtJa(typed.ev_injected_at_ja);
      setActionError(null);
      return typed;
    },
    []
  );

  const pause = useCallback(async (): Promise<void> => {
    try {
      await postSimControl({ action: "pause" });
    } catch (err: unknown) {
      setActionError(
        err instanceof Error ? err.message : "Failed to pause simulation"
      );
    }
  }, [postSimControl]);

  const setSpeed = useCallback(
    async (nextSpeed: SpeedMultiplier): Promise<void> => {
      try {
        await postSimControl({
          action: "set_speed",
          speed_multiplier: nextSpeed,
        });
      } catch (err: unknown) {
        setActionError(
          err instanceof Error ? err.message : "Failed to update speed"
        );
      }
    },
    [postSimControl]
  );

  const processFrame = useCallback(
    (frame: ABFrameSnapshot): void => {
      setLatestFrame(frame);
      setScenarioState(frame.scenario);

      if (
        frame.baseline.kpis.ev_completed &&
        frame.aegisflow.kpis.ev_completed
      ) {
        setIsRunning(false);
      }

      const nextPoint: ChartHistoryPoint = {
        tick: frame.tick,
        baselineJbQueueM: frame.baseline.states.J_B.queue_length_m,
        aegisflowJbQueueM: frame.aegisflow.states.J_B.queue_length_m,
        baselinePeakQueueM: frame.baseline.kpis.peak_queue_length_m,
        aegisflowPeakQueueM: frame.aegisflow.kpis.peak_queue_length_m,
      };

      setChartHistory((prev) => {
        if (frame.tick === 0) {
          return [nextPoint];
        }
        const withoutDup = prev.filter((pt) => pt.tick !== frame.tick);
        return [...withoutDup, nextPoint].slice(-MAX_CHART_HISTORY);
      });

      const newEvents: ShieldEventEntry[] = [];
      for (const jid of JUNCTIONS) {
        const cmd = frame.aegisflow.commands[jid];
        const prevPhase = lastPhasesRef.current[jid];
        const phaseChanged =
          prevPhase !== undefined && prevPhase !== cmd.approved_phase;
        lastPhasesRef.current[jid] = cmd.approved_phase;

        const isNotable =
          cmd.shield_decision !== "APPROVED" ||
          phaseChanged ||
          frame.tick === 0 ||
          cmd.original_action_type !== "HOLD";

        if (isNotable) {
          newEvents.push({
            id: `${frame.tick}-${jid}-${cmd.timestamp}`,
            tick: frame.tick,
            timestamp: cmd.timestamp,
            junctionId: jid,
            decision: cmd.shield_decision,
            originalAction: cmd.original_action_type,
            approvedPhase: cmd.approved_phase,
            approvedDurationS: cmd.approved_duration_s,
            violatedInvariants: cmd.violated_invariants,
            auditMessage: cmd.audit_message,
          });
        }
      }

      if (frame.tick === 0) {
        setShieldEvents(newEvents.reverse());
      } else if (newEvents.length > 0) {
        setShieldEvents((prev) => {
          const existingIds = new Set(prev.map((item) => item.id));
          const uniqueIncoming = newEvents
            .filter((item) => !existingIds.has(item.id))
            .reverse();
          return [...uniqueIncoming, ...prev].slice(0, MAX_SHIELD_EVENTS);
        });
      }

      if (pendingStepRef.current) {
        pendingStepRef.current = false;
        const restore = restoreSpeedRef.current;
        restoreSpeedRef.current = null;
        void (async () => {
          await pause();
          if (restore !== null && restore !== 4) {
            await setSpeed(restore);
          }
        })();
      }
    },
    [pause, setSpeed]
  );

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let unmounted = false;
    let retryDelayMs = 1000;

    function connect(): void {
      if (unmounted) {
        return;
      }
      setConnectionStatus((prev) =>
        prev === "connected" ? "connected" : "reconnecting"
      );

      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        if (unmounted) {
          return;
        }
        retryDelayMs = 1000;
        setConnectionStatus("connected");
        setActionError(null);
      };

      ws.onmessage = (event: MessageEvent<string>) => {
        if (unmounted) {
          return;
        }
        try {
          const parsed: unknown = JSON.parse(event.data);
          if (isABFrameSnapshot(parsed)) {
            processFrame(parsed);
          }
        } catch {
          // Ignore malformed non-JSON messages.
        }
      };

      ws.onerror = () => {
        if (!unmounted) {
          setConnectionStatus("reconnecting");
        }
      };

      ws.onclose = () => {
        if (unmounted) {
          return;
        }
        setConnectionStatus(retryDelayMs >= 4000 ? "offline" : "reconnecting");
        reconnectTimer = window.setTimeout(() => {
          retryDelayMs = Math.min(5000, Math.round(retryDelayMs * 1.5));
          connect();
        }, retryDelayMs);
      };
    }

    connect();

    return () => {
      unmounted = true;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
      if (ws !== null) {
        ws.close();
      }
    };
  }, [processFrame]);

  const start = useCallback(async (): Promise<void> => {
    try {
      await postSimControl({
        action: "start",
        scenario,
        speed_multiplier: speedMultiplier,
      });
    } catch (err: unknown) {
      setActionError(
        err instanceof Error ? err.message : "Failed to start simulation"
      );
    }
  }, [postSimControl, scenario, speedMultiplier]);

  const reset = useCallback(async (): Promise<void> => {
    try {
      pendingStepRef.current = false;
      lastPhasesRef.current = {};
      setChartHistory([]);
      setShieldEvents([]);
      await postSimControl({ action: "reset", scenario });
    } catch (err: unknown) {
      setActionError(
        err instanceof Error ? err.message : "Failed to reset simulation"
      );
    }
  }, [postSimControl, scenario]);

  const step = useCallback(async (): Promise<void> => {
    try {
      restoreSpeedRef.current = speedMultiplier;
      pendingStepRef.current = true;
      await postSimControl({
        action: "start",
        scenario,
        speed_multiplier: 4,
      });
    } catch (err: unknown) {
      pendingStepRef.current = false;
      restoreSpeedRef.current = null;
      setActionError(
        err instanceof Error ? err.message : "Failed to step simulation"
      );
    }
  }, [postSimControl, scenario, speedMultiplier]);

  const setScenario = useCallback(
    async (nextScenario: ScenarioPreset): Promise<void> => {
      try {
        pendingStepRef.current = false;
        lastPhasesRef.current = {};
        setChartHistory([]);
        setShieldEvents([]);
        await postSimControl({
          action: "set_scenario",
          scenario: nextScenario,
        });
      } catch (err: unknown) {
        setActionError(
          err instanceof Error ? err.message : "Failed to switch scenario"
        );
      }
    },
    [postSimControl]
  );

  const injectEv = useCallback(async (): Promise<void> => {
    try {
      await postSimControl({ action: "inject_ev" });
      if (!isRunning) {
        await postSimControl({
          action: "start",
          scenario,
          speed_multiplier: speedMultiplier,
        });
      }
    } catch (err: unknown) {
      setActionError(
        err instanceof Error ? err.message : "Failed to dispatch EV"
      );
    }
  }, [isRunning, postSimControl, scenario, speedMultiplier]);

  const runBenchmark = useCallback(
    async (targetScenario?: ScenarioPreset): Promise<BenchmarkSummary> => {
      const activeScenario = targetScenario ?? scenario;
      const response = await fetch(
        `${API_BASE_URL}/api/v1/sim/benchmark?scenario=${encodeURIComponent(activeScenario)}&seed=42&max_ticks=150`,
        { method: "GET" }
      );
      if (!response.ok) {
        throw new Error(`Benchmark HTTP ${response.status}`);
      }
      const data: unknown = await response.json();
      if (!isRecord(data) || !isRecord(data.comparison_kpis)) {
        throw new Error("Invalid BenchmarkSummary payload");
      }
      return data as unknown as BenchmarkSummary;
    },
    [scenario]
  );

  return {
    latestFrame,
    chartHistory,
    shieldEvents,
    connectionStatus,
    isRunning,
    scenario,
    speedMultiplier,
    evInjectedAtJa,
    actionError,
    start,
    pause,
    reset,
    step,
    setScenario,
    setSpeed,
    injectEv,
    runBenchmark,
  };
}
