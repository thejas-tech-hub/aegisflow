"""Configuration schema for the AegisFlow physics-informed spillback predictor."""

from pydantic import BaseModel, ConfigDict, Field

from schemas.contracts import JunctionID


def _default_corridor_topology() -> dict[JunctionID, JunctionID | None]:
    """Return the default linear 3-junction corridor topology (J_A -> J_B -> J_C)."""
    return {
        JunctionID.J_A: JunctionID.J_B,
        JunctionID.J_B: JunctionID.J_C,
        JunctionID.J_C: None,
    }


class PredictorConfig(BaseModel):
    """Pydantic v2 configuration for physics-informed queue and spillback forecasting."""

    model_config = ConfigDict(extra="forbid")

    default_horizon_s: int = Field(
        default=45,
        ge=30,
        le=60,
        description="Default forecast lookahead horizon in seconds (30 to 60).",
    )
    spillback_threshold: float = Field(
        default=0.78,
        gt=0.0,
        le=1.5,
        description="Spillback risk index threshold above which spillback is imminent.",
    )
    saturation_discharge_vps: float = Field(
        default=0.65,
        gt=0.0,
        description="Arterial saturation discharge rate during EW_GREEN (veh/s).",
    )
    effective_pcu_spacing_m: float = Field(
        default=6.5,
        gt=0.0,
        description="Effective longitudinal road length per PCU in Indian mixed queues (m).",
    )
    corridor_topology: dict[JunctionID, JunctionID | None] = Field(
        default_factory=_default_corridor_topology,
        description="Directed mapping from each upstream junction to its downstream neighbor.",
    )
    history_window: int = Field(
        default=30,
        ge=2,
        description="Rolling history length (ticks) retained per junction.",
    )
    effective_lanes: float = Field(
        default=2.0,
        gt=0.0,
        description="Effective directional arterial queue lanes for spatial translation.",
    )
