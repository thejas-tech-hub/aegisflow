"""Configuration schema for the AegisFlow spillback-aware corridor orchestrator."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.contracts import JunctionID


def _default_corridor_order() -> list[JunctionID]:
    """Return default topological corridor evaluation order (upstream -> downstream)."""
    return [JunctionID.J_A, JunctionID.J_B, JunctionID.J_C]


class OrchestratorConfig(BaseModel):
    """Pydantic v2 configuration for multi-junction rolling-horizon orchestration."""

    model_config = ConfigDict(extra="forbid")

    ev_flush_window_min_s: float = Field(
        default=10.0,
        ge=0.0,
        description="Minimum EV ETA (seconds) for proactive pre-arrival queue flush.",
    )
    ev_flush_window_max_s: float = Field(
        default=55.0,
        gt=0.0,
        description="Maximum EV ETA (seconds) to trigger proactive queue flush.",
    )
    ev_extension_window_s: float = Field(
        default=15.0,
        gt=0.0,
        description="EV ETA threshold (seconds) to hold/extend active arterial green.",
    )
    flush_occupancy_trigger: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description="Occupancy threshold signaling standing queues requiring flushing.",
    )
    metering_spillback_trigger: float = Field(
        default=0.78,
        gt=0.0,
        le=1.5,
        description="Downstream spillback risk trigger for upstream inflow metering.",
    )
    max_pressure_switch_threshold: float = Field(
        default=15.0,
        ge=0.0,
        description="Pressure differential required to trigger non-EV phase recovery.",
    )
    corridor_order: list[JunctionID] = Field(
        default_factory=_default_corridor_order,
        min_length=1,
        description="Ordered list of junctions from upstream to downstream.",
    )

    @model_validator(mode="after")
    def _validate_flush_window(self) -> "OrchestratorConfig":
        """Ensure proactive flush window upper bound is >= lower bound."""
        if self.ev_flush_window_max_s < self.ev_flush_window_min_s:
            raise ValueError(
                "ev_flush_window_max_s must be greater than or equal to ev_flush_window_min_s"
            )
        return self
