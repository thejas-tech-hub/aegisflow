export interface HealthResponse {
  status: string;
  service: string;
}

export type GatewayConnectionState = "checking" | "connected" | "disconnected";
