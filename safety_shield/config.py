"""Municipal signal safety timing configuration for AegisFlow."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SafetyConfig(BaseModel):
    """Deterministic municipal signal timing bounds and clearance defaults."""

    model_config = ConfigDict(extra="forbid")

    min_green_s: float = Field(
        default=10.0,
        gt=0.0,
        description="Minimum guaranteed green phase duration (seconds).",
    )
    max_green_s: float = Field(
        default=75.0,
        gt=0.0,
        description="Maximum allowed continuous green phase duration (seconds).",
    )
    yellow_duration_s: float = Field(
        default=3.0,
        gt=0.0,
        description="Mandatory amber/yellow clearance duration (seconds).",
    )
    all_red_duration_s: float = Field(
        default=2.0,
        gt=0.0,
        description="Mandatory all-red clearance interval duration (seconds).",
    )
    max_cross_street_red_s: float = Field(
        default=110.0,
        gt=0.0,
        description="Maximum opposing street wait time before anti-starvation override.",
    )

    @model_validator(mode="after")
    def _validate_green_bounds(self) -> "SafetyConfig":
        """Ensure max_green_s is not less than min_green_s."""
        if self.max_green_s < self.min_green_s:
            raise ValueError("max_green_s must be greater than or equal to min_green_s")
        return self
