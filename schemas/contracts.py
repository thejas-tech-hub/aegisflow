"""Core inter-module Pydantic v2 data contracts for AegisFlow.

Defines strict typed schemas shared across perception/, sim/, predictor/,
orchestrator/, safety_shield/, backend/, and frontend/.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JunctionID(StrEnum):
    """Identifier for the three coordinated corridor junctions."""

    J_A = "J_A"
    J_B = "J_B"
    J_C = "J_C"


class SignalPhase(StrEnum):
    """Standardized 6-state NEMA/Indian municipal signal phase ring."""

    NS_GREEN = "NS_GREEN"
    NS_YELLOW = "NS_YELLOW"
    ALL_RED_TO_EW = "ALL_RED_TO_EW"
    EW_GREEN = "EW_GREEN"
    EW_YELLOW = "EW_YELLOW"
    ALL_RED_TO_NS = "ALL_RED_TO_NS"


class ControlActionType(StrEnum):
    """Advisory control actions proposed by the orchestrator."""

    HOLD = "HOLD"
    GREEN_EXTENSION = "GREEN_EXTENSION"
    RED_TRUNCATION = "RED_TRUNCATION"
    UPSTREAM_METERING = "UPSTREAM_METERING"
    RECOVERY = "RECOVERY"


class ShieldDecision(StrEnum):
    """Verification outcome emitted by safety_shield/."""

    APPROVED = "APPROVED"
    CLIPPED = "CLIPPED"
    VETOED = "VETOED"


class VehicleMix(BaseModel):
    """Heterogeneous vehicle counts observed on a junction approach."""

    model_config = ConfigDict(extra="forbid")

    motorcycles: int = Field(
        default=0,
        ge=0,
        description="Count of two-wheelers / motorcycles.",
    )
    auto_rickshaws: int = Field(
        default=0,
        ge=0,
        description="Count of three-wheeled auto-rickshaws.",
    )
    cars: int = Field(
        default=0,
        ge=0,
        description="Count of passenger cars and light vans.",
    )
    buses_trucks: int = Field(
        default=0,
        ge=0,
        description="Count of heavy buses and trucks.",
    )
    emergency_vehicles: int = Field(
        default=0,
        ge=0,
        description="Count of detected emergency vehicles (ambulances, fire trucks).",
    )


class JunctionStatePacket(BaseModel):
    """Unified junction telemetry emitted identically by perception/ and sim/."""

    model_config = ConfigDict(extra="forbid")

    junction_id: JunctionID = Field(
        description="Target junction identifier.",
    )
    timestamp: float = Field(
        ge=0.0,
        description="Simulation or epoch timestamp in seconds.",
    )
    source: Literal["cctv", "sumo", "mock"] = Field(
        description="Telemetry producer origin.",
    )
    active_phase: SignalPhase = Field(
        description="Currently active signal phase at the junction.",
    )
    phase_elapsed_s: float = Field(
        ge=0.0,
        description="Elapsed duration in the active signal phase (seconds).",
    )
    spatial_occupancy_ratio: float = Field(
        ge=0.0,
        le=1.0,
        description="BEV ground-plane road area occupancy ratio (0.0 to 1.0).",
    )
    pcu_density: float = Field(
        ge=0.0,
        description="Indian Passenger Car Unit (PCU) weighted density.",
    )
    queue_length_m: float = Field(
        ge=0.0,
        description="Estimated physical queue length along approach (meters).",
    )
    link_length_m: float = Field(
        default=300.0,
        gt=0.0,
        description="Total upstream approach link length (meters).",
    )
    avg_speed_mps: float = Field(
        ge=0.0,
        description="Mean vehicle speed on the approach (meters/second).",
    )
    inflow_rate_vps: float = Field(
        ge=0.0,
        description="Observed approach inflow rate (vehicles/second).",
    )
    outflow_rate_vps: float = Field(
        ge=0.0,
        description="Observed junction discharge outflow rate (vehicles/second).",
    )
    vehicle_mix: VehicleMix = Field(
        description="Classified heterogeneous vehicle counts.",
    )
    ev_detected: bool = Field(
        description="Whether an emergency vehicle is actively detected.",
    )
    ev_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Multi-modal EV detection confidence score (0.0 to 1.0).",
    )
    ev_eta_s: float | None = Field(
        default=None,
        ge=0.0,
        description="Estimated time of arrival of the EV at the stop line (seconds).",
    )
    ev_distance_m: float | None = Field(
        default=None,
        ge=0.0,
        description="Distance of the EV from the junction stop line (meters).",
    )


class SpillbackForecast(BaseModel):
    """Short-horizon queue and spillback prediction emitted by predictor/."""

    model_config = ConfigDict(extra="forbid")

    junction_id: JunctionID = Field(
        description="Target junction identifier.",
    )
    timestamp: float = Field(
        ge=0.0,
        description="Forecast reference timestamp in seconds.",
    )
    horizon_s: int = Field(
        ge=30,
        le=60,
        description="Forecast lookahead horizon in seconds (30 to 60).",
    )
    predicted_occupancy_ratio: float = Field(
        ge=0.0,
        le=1.0,
        description="Forecasted BEV spatial occupancy ratio at horizon.",
    )
    predicted_queue_length_m: float = Field(
        ge=0.0,
        description="Forecasted queue length at horizon (meters).",
    )
    spillback_risk_index: float = Field(
        ge=0.0,
        le=1.5,
        description="Normalized spillback severity index (0.0 to 1.5; >=1.0 critical).",
    )
    spillback_imminent: bool = Field(
        description="True when queue is projected to spill back upstream.",
    )
    predicted_ev_eta_s: float | None = Field(
        default=None,
        ge=0.0,
        description="Forecasted EV arrival time at the junction (seconds).",
    )


class ProposedControlAction(BaseModel):
    """Advisory signal control action emitted by orchestrator/."""

    model_config = ConfigDict(extra="forbid")

    junction_id: JunctionID = Field(
        description="Target junction identifier.",
    )
    timestamp: float = Field(
        ge=0.0,
        description="Proposal creation timestamp in seconds.",
    )
    target_phase: SignalPhase = Field(
        description="Requested signal phase to maintain or transition toward.",
    )
    action_type: ControlActionType = Field(
        description="Type of advisory corridor control action.",
    )
    requested_duration_s: float = Field(
        ge=0.0,
        description="Requested phase hold or extension duration (seconds).",
    )
    reason: str = Field(
        description="Human-readable rationale for the proposed action.",
    )
    priority_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Normalized urgency/priority score (0.0 to 1.0).",
    )


class VerifiedSignalCommand(BaseModel):
    """Safety-verified signal command emitted exclusively by safety_shield/."""

    model_config = ConfigDict(extra="forbid")

    junction_id: JunctionID = Field(
        description="Target junction identifier.",
    )
    timestamp: float = Field(
        ge=0.0,
        description="Command verification timestamp in seconds.",
    )
    approved_phase: SignalPhase = Field(
        description="Final verified signal phase approved for actuation.",
    )
    approved_duration_s: float = Field(
        ge=0.0,
        description="Final verified duration in seconds.",
    )
    shield_decision: ShieldDecision = Field(
        description="Verification verdict: APPROVED, CLIPPED, or VETOED.",
    )
    original_action_type: ControlActionType = Field(
        description="Original advisory action type evaluated by the shield.",
    )
    violated_invariants: list[str] = Field(
        default_factory=list,
        description="List of municipal safety invariants violated (empty if approved).",
    )
    audit_message: str = Field(
        description="Deterministic audit trail explanation for the decision.",
    )
