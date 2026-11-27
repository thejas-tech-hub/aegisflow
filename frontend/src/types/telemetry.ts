/** Strict TypeScript contracts mirroring schemas/contracts.py, orchestrator/ab_runner.py, and backend/main.py. */

export type JunctionID = "J_A" | "J_B" | "J_C";

export type SignalPhase =
  | "NS_GREEN"
  | "NS_YELLOW"
  | "ALL_RED_TO_EW"
  | "EW_GREEN"
  | "EW_YELLOW"
  | "ALL_RED_TO_NS";

export type ControlActionType =
  | "HOLD"
  | "GREEN_EXTENSION"
  | "RED_TRUNCATION"
  | "UPSTREAM_METERING"
  | "RECOVERY";

export type ShieldDecision = "APPROVED" | "CLIPPED" | "VETOED";

export type ScenarioPreset =
  | "peak_spillback"
  | "moderate_mixed"
  | "severe_gridlock";

export type SpeedMultiplier = 1 | 2 | 4;

export type SimControlAction =
  | "start"
  | "pause"
  | "resume"
  | "reset"
  | "set_scenario"
  | "set_speed"
  | "inject_ev";

export type SocketConnectionStatus = "connected" | "reconnecting" | "offline";

export interface VehicleMix {
  motorcycles: number;
  auto_rickshaws: number;
  cars: number;
  buses_trucks: number;
  emergency_vehicles: number;
}

export interface JunctionStatePacket {
  junction_id: JunctionID;
  timestamp: number;
  source: "cctv" | "sumo" | "mock";
  active_phase: SignalPhase;
  phase_elapsed_s: number;
  spatial_occupancy_ratio: number;
  pcu_density: number;
  queue_length_m: number;
  link_length_m: number;
  avg_speed_mps: number;
  inflow_rate_vps: number;
  outflow_rate_vps: number;
  vehicle_mix: VehicleMix;
  ev_detected: boolean;
  ev_confidence: number;
  ev_eta_s: number | null;
  ev_distance_m: number | null;
}

export interface SpillbackForecast {
  junction_id: JunctionID;
  timestamp: number;
  horizon_s: number;
  predicted_occupancy_ratio: number;
  predicted_queue_length_m: number;
  spillback_risk_index: number;
  spillback_imminent: boolean;
  predicted_ev_eta_s: number | null;
}

export interface ProposedControlAction {
  junction_id: JunctionID;
  timestamp: number;
  target_phase: SignalPhase;
  action_type: ControlActionType;
  requested_duration_s: number;
  reason: string;
  priority_score: number;
}

export interface VerifiedSignalCommand {
  junction_id: JunctionID;
  timestamp: number;
  approved_phase: SignalPhase;
  approved_duration_s: number;
  shield_decision: ShieldDecision;
  original_action_type: ControlActionType;
  violated_invariants: string[];
  audit_message: string;
}

export interface ShieldAuditSummary {
  APPROVED: number;
  CLIPPED: number;
  VETOED: number;
}

export interface TrackKPIs {
  ev_travel_time_s: number | null;
  ev_stopped_time_s: number;
  peak_queue_length_m: number;
  spillback_ticks: number;
  ev_completed: boolean;
  shield_audit_summary: ShieldAuditSummary;
}

export type ApiPulseType =
  | "EV_SPILLBACK_ALERT"
  | "EV_GREEN_WAVE_HANDOFF"
  | "SPILLBACK_METERING_BACKPRESSURE";

export interface ApiPulsePacket {
  from: JunctionID;
  to: JunctionID;
  type: ApiPulseType;
  eta_s: number | null;
  risk_index: number;
}

export interface BaselineTrackSnapshot {
  states: Record<JunctionID, JunctionStatePacket>;
  commands: Record<JunctionID, VerifiedSignalCommand>;
  ev_position_m: number;
  ev_speed_mps: number;
  ev_trapped_in_spillback: boolean;
  kpis: TrackKPIs;
}

export interface AegisFlowTrackSnapshot {
  states: Record<JunctionID, JunctionStatePacket>;
  forecasts: Record<JunctionID, SpillbackForecast>;
  proposals: Record<JunctionID, ProposedControlAction>;
  commands: Record<JunctionID, VerifiedSignalCommand>;
  ev_position_m: number;
  ev_speed_mps: number;
  ev_trapped_in_spillback: boolean;
  active_api_packets: ApiPulsePacket[];
  kpis: TrackKPIs;
}

export interface ComparisonKPIs {
  ev_travel_time_reduction_pct: number;
  ev_travel_time_saved_s: number;
  ev_stopped_time_reduction_pct: number;
  ev_stopped_time_saved_s: number;
  peak_queue_reduction_pct: number;
  spillback_ticks_reduction_pct: number;
}

export interface ABFrameSnapshot {
  tick: number;
  scenario: ScenarioPreset;
  baseline: BaselineTrackSnapshot;
  aegisflow: AegisFlowTrackSnapshot;
  comparison_kpis: ComparisonKPIs;
}

export interface SimControlRequest {
  action: SimControlAction;
  scenario?: ScenarioPreset;
  speed_multiplier?: SpeedMultiplier;
}

export interface SimControlResponse {
  status: string;
  is_running: boolean;
  scenario: ScenarioPreset;
  speed_multiplier: SpeedMultiplier;
  tick: number;
  ev_injected_at_ja: boolean;
  message: string;
}

export interface BenchmarkSummary {
  scenario: ScenarioPreset;
  total_ticks: number;
  baseline_kpis: TrackKPIs;
  aegisflow_kpis: TrackKPIs;
  comparison_kpis: ComparisonKPIs;
  final_snapshot: ABFrameSnapshot;
}

export interface ChartHistoryPoint {
  tick: number;
  baselineJbQueueM: number;
  aegisflowJbQueueM: number;
  baselinePeakQueueM: number;
  aegisflowPeakQueueM: number;
}

export interface ShieldEventEntry {
  id: string;
  tick: number;
  timestamp: number;
  junctionId: JunctionID;
  decision: ShieldDecision;
  originalAction: ControlActionType;
  approvedPhase: SignalPhase;
  approvedDurationS: number;
  violatedInvariants: string[];
  auditMessage: string;
}
