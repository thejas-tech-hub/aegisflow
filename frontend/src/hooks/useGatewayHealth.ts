import { useEffect, useState } from "react";
import type { GatewayConnectionState, HealthResponse } from "../types/gateway";

const GATEWAY_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

interface UseGatewayHealthResult {
  state: GatewayConnectionState;
  health: HealthResponse | null;
  error: string | null;
}

function isHealthResponse(payload: unknown): payload is HealthResponse {
  if (typeof payload !== "object" || payload === null) {
    return false;
  }
  const record = payload as Record<string, unknown>;
  return (
    typeof record.status === "string" && typeof record.service === "string"
  );
}

export function useGatewayHealth(): UseGatewayHealthResult {
  const [state, setState] = useState<GatewayConnectionState>("checking");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function checkHealth(): Promise<void> {
      try {
        const response = await fetch(`${GATEWAY_BASE_URL}/api/v1/health`, {
          method: "GET",
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`Gateway returned HTTP ${response.status}`);
        }

        const data: unknown = await response.json();
        if (!isHealthResponse(data) || data.status !== "ok") {
          throw new Error("Invalid gateway health payload");
        }

        setHealth(data);
        setState("connected");
        setError(null);
      } catch (err: unknown) {
        if (controller.signal.aborted) {
          return;
        }
        const message =
          err instanceof Error ? err.message : "Failed to reach gateway";
        setHealth(null);
        setState("disconnected");
        setError(message);
      }
    }

    void checkHealth();

    return () => {
      controller.abort();
    };
  }, []);

  return { state, health, error };
}
