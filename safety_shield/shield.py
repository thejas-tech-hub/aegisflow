"""Deterministic municipal safety shield verifying all signal control proposals.

Enforces 5 non-negotiable signal invariants in strict priority order:
1. Clearance Lock (MANDATORY_CLEARANCE)
2. Anti-Starvation (MAX_RED_STARVATION)
3. Illegal Direct Jump (CONFLICT_MUTEX / MANDATORY_CLEARANCE)
4. Minimum Green Lock (MIN_GREEN_LOCK)
5. Duration Clamping (DURATION_BOUNDS)
"""

from pydantic import BaseModel, ConfigDict, Field

from safety_shield.config import SafetyConfig
from schemas.contracts import (
    ControlActionType,
    JunctionID,
    JunctionStatePacket,
    ProposedControlAction,
    ShieldDecision,
    SignalPhase,
    VerifiedSignalCommand,
)

_MAX_AUDIT_LOG_ENTRIES = 500

_GREEN_PHASES: frozenset[SignalPhase] = frozenset(
    {SignalPhase.NS_GREEN, SignalPhase.EW_GREEN}
)
_YELLOW_TO_ALL_RED: dict[SignalPhase, SignalPhase] = {
    SignalPhase.NS_YELLOW: SignalPhase.ALL_RED_TO_EW,
    SignalPhase.EW_YELLOW: SignalPhase.ALL_RED_TO_NS,
}
_ALL_RED_TO_GREEN: dict[SignalPhase, SignalPhase] = {
    SignalPhase.ALL_RED_TO_EW: SignalPhase.EW_GREEN,
    SignalPhase.ALL_RED_TO_NS: SignalPhase.NS_GREEN,
}
_GREEN_TO_YELLOW: dict[SignalPhase, SignalPhase] = {
    SignalPhase.NS_GREEN: SignalPhase.NS_YELLOW,
    SignalPhase.EW_GREEN: SignalPhase.EW_YELLOW,
}
_OPPOSING_GREEN: dict[SignalPhase, SignalPhase] = {
    SignalPhase.NS_GREEN: SignalPhase.EW_GREEN,
    SignalPhase.EW_GREEN: SignalPhase.NS_GREEN,
}


class JunctionSafetyState(BaseModel):
    """Per-junction runtime state tracked by DeterministicSafetyShield."""

    model_config = ConfigDict(extra="forbid")

    active_phase: SignalPhase = Field(
        description="Latest observed signal phase at the junction.",
    )
    phase_elapsed_s: float = Field(
        default=0.0,
        ge=0.0,
        description="Elapsed seconds in the active phase.",
    )
    opposing_red_wait_s: float = Field(
        default=0.0,
        ge=0.0,
        description="Accumulated wait time of the opposing street approach (seconds).",
    )
    pending_target_phase: SignalPhase | None = Field(
        default=None,
        description="Target green phase queued behind an active clearance sequence.",
    )
    last_timestamp_s: float | None = Field(
        default=None,
        ge=0.0,
        description="Timestamp of the previous verified packet for dt tracking.",
    )
    audit_log: list[VerifiedSignalCommand] = Field(
        default_factory=list,
        description="Bounded per-junction history of issued commands.",
    )


class DeterministicSafetyShield:
    """Deterministic municipal safety verifier for advisory orchestrator actions."""

    def __init__(self, config: SafetyConfig | None = None) -> None:
        """Initialize the safety shield with municipal timing configuration."""
        self.config: SafetyConfig = config or SafetyConfig()
        self.junction_states: dict[JunctionID, JunctionSafetyState] = {}
        self.audit_log: list[VerifiedSignalCommand] = []

    def _update_junction_state(
        self, state: JunctionStatePacket
    ) -> JunctionSafetyState:
        """Synchronize per-junction safety tracking from the incoming packet."""
        existing = self.junction_states.get(state.junction_id)
        if existing is None:
            initial_wait = (
                state.phase_elapsed_s if state.active_phase in _GREEN_PHASES else 0.0
            )
            j_state = JunctionSafetyState(
                active_phase=state.active_phase,
                phase_elapsed_s=state.phase_elapsed_s,
                opposing_red_wait_s=initial_wait,
                pending_target_phase=None,
                last_timestamp_s=state.timestamp,
            )
            self.junction_states[state.junction_id] = j_state
            return j_state

        dt = (
            max(0.0, state.timestamp - existing.last_timestamp_s)
            if existing.last_timestamp_s is not None
            else 0.0
        )

        if state.active_phase != existing.active_phase:
            if state.active_phase in _GREEN_PHASES:
                existing.opposing_red_wait_s = state.phase_elapsed_s
                if existing.pending_target_phase == state.active_phase:
                    existing.pending_target_phase = None
            else:
                existing.opposing_red_wait_s += dt
        else:
            existing.opposing_red_wait_s += dt

        existing.active_phase = state.active_phase
        existing.phase_elapsed_s = state.phase_elapsed_s
        existing.last_timestamp_s = state.timestamp
        return existing

    def _record_command(
        self,
        j_state: JunctionSafetyState,
        command: VerifiedSignalCommand,
    ) -> VerifiedSignalCommand:
        """Append a verified command to bounded global and per-junction audit logs."""
        self.audit_log.append(command)
        if len(self.audit_log) > _MAX_AUDIT_LOG_ENTRIES:
            self.audit_log = self.audit_log[-_MAX_AUDIT_LOG_ENTRIES:]

        j_state.audit_log.append(command)
        if len(j_state.audit_log) > _MAX_AUDIT_LOG_ENTRIES:
            j_state.audit_log = j_state.audit_log[-_MAX_AUDIT_LOG_ENTRIES:]

        return command

    def _build_command(
        self,
        state: JunctionStatePacket,
        proposal: ProposedControlAction,
        approved_phase: SignalPhase,
        approved_duration_s: float,
        decision: ShieldDecision,
        violated_invariants: list[str],
        audit_message: str,
    ) -> VerifiedSignalCommand:
        """Construct a VerifiedSignalCommand anchored to the incoming proposal."""
        return VerifiedSignalCommand(
            junction_id=state.junction_id,
            timestamp=state.timestamp,
            approved_phase=approved_phase,
            approved_duration_s=round(max(0.0, approved_duration_s), 3),
            shield_decision=decision,
            original_action_type=proposal.action_type,
            violated_invariants=violated_invariants,
            audit_message=audit_message,
        )

    def _handle_clearance_phase(
        self,
        state: JunctionStatePacket,
        proposal: ProposedControlAction,
        j_state: JunctionSafetyState,
    ) -> VerifiedSignalCommand:
        """Enforce Invariant 1 (MANDATORY_CLEARANCE) during yellow and all-red."""
        active = state.active_phase
        if active in _YELLOW_TO_ALL_RED:
            required_s = self.config.yellow_duration_s
            next_phase = _YELLOW_TO_ALL_RED[active]
            next_duration = self.config.all_red_duration_s
            phase_label = "yellow"
        else:
            required_s = self.config.all_red_duration_s
            next_phase = _ALL_RED_TO_GREEN[active]
            next_duration = self.config.min_green_s
            phase_label = "all-red"

        if state.phase_elapsed_s < required_s:
            remaining_s = required_s - state.phase_elapsed_s
            if (
                proposal.target_phase != active
                or proposal.action_type == ControlActionType.RED_TRUNCATION
            ):
                return self._build_command(
                    state=state,
                    proposal=proposal,
                    approved_phase=active,
                    approved_duration_s=remaining_s,
                    decision=ShieldDecision.VETOED,
                    violated_invariants=["MANDATORY_CLEARANCE"],
                    audit_message=(
                        f"VETOED {proposal.action_type} toward {proposal.target_phase}: "
                        f"{active} {phase_label} clearance incomplete "
                        f"({state.phase_elapsed_s:.1f}s < {required_s:.1f}s)."
                    ),
                )
            return self._build_command(
                state=state,
                proposal=proposal,
                approved_phase=active,
                approved_duration_s=remaining_s,
                decision=ShieldDecision.APPROVED,
                violated_invariants=[],
                audit_message=(
                    f"APPROVED hold on {active} ({remaining_s:.1f}s remaining "
                    f"in {phase_label} clearance)."
                ),
            )

        # Clearance interval has elapsed: advance strictly along the legal FSM ring.
        if next_phase in _GREEN_PHASES:
            clamped_green = min(
                max(proposal.requested_duration_s, self.config.min_green_s),
                self.config.max_green_s,
            )
            if proposal.target_phase == next_phase:
                j_state.pending_target_phase = None
                if clamped_green != proposal.requested_duration_s:
                    return self._build_command(
                        state=state,
                        proposal=proposal,
                        approved_phase=next_phase,
                        approved_duration_s=clamped_green,
                        decision=ShieldDecision.CLIPPED,
                        violated_invariants=["DURATION_BOUNDS"],
                        audit_message=(
                            f"Advance {active} -> {next_phase} after {phase_label} "
                            f"clearance; duration clipped from "
                            f"{proposal.requested_duration_s:.1f}s to {clamped_green:.1f}s."
                        ),
                    )
                return self._build_command(
                    state=state,
                    proposal=proposal,
                    approved_phase=next_phase,
                    approved_duration_s=clamped_green,
                    decision=ShieldDecision.APPROVED,
                    violated_invariants=[],
                    audit_message=(
                        f"APPROVED transition {active} -> {next_phase} "
                        f"for {clamped_green:.1f}s after {phase_label} clearance."
                    ),
                )

            j_state.pending_target_phase = None
            return self._build_command(
                state=state,
                proposal=proposal,
                approved_phase=next_phase,
                approved_duration_s=next_duration,
                decision=ShieldDecision.VETOED,
                violated_invariants=["MANDATORY_CLEARANCE"],
                audit_message=(
                    f"VETOED {proposal.target_phase} at end of {active}; "
                    f"forcing legal FSM transition to {next_phase}."
                ),
            )

        # Yellow elapsed -> mandatory ALL_RED transition.
        if proposal.target_phase == next_phase:
            return self._build_command(
                state=state,
                proposal=proposal,
                approved_phase=next_phase,
                approved_duration_s=next_duration,
                decision=ShieldDecision.APPROVED,
                violated_invariants=[],
                audit_message=(
                    f"APPROVED transition {active} -> {next_phase} "
                    f"for {next_duration:.1f}s."
                ),
            )

        return self._build_command(
            state=state,
            proposal=proposal,
            approved_phase=next_phase,
            approved_duration_s=next_duration,
            decision=ShieldDecision.CLIPPED,
            violated_invariants=["MANDATORY_CLEARANCE"],
            audit_message=(
                f"CLIPPED {proposal.target_phase} after {active}; "
                f"enforcing mandatory all-red {next_phase} ({next_duration:.1f}s)."
            ),
        )

    def verify(
        self,
        state: JunctionStatePacket,
        proposal: ProposedControlAction,
    ) -> VerifiedSignalCommand:
        """Verify an advisory orchestrator action against all 5 safety invariants."""
        j_state = self._update_junction_state(state)
        active = state.active_phase

        # 1. Clearance Lock (MANDATORY_CLEARANCE)
        if active not in _GREEN_PHASES:
            cmd = self._handle_clearance_phase(state, proposal, j_state)
            return self._record_command(j_state, cmd)

        # 2. Anti-Starvation (MAX_RED_STARVATION)
        if (
            j_state.opposing_red_wait_s > self.config.max_cross_street_red_s
            and state.phase_elapsed_s >= self.config.min_green_s
            and (
                proposal.target_phase == active
                or proposal.action_type
                in (ControlActionType.HOLD, ControlActionType.GREEN_EXTENSION)
            )
        ):
            yellow_phase = _GREEN_TO_YELLOW[active]
            starved_phase = _OPPOSING_GREEN[active]
            j_state.pending_target_phase = starved_phase
            cmd = self._build_command(
                state=state,
                proposal=proposal,
                approved_phase=yellow_phase,
                approved_duration_s=self.config.yellow_duration_s,
                decision=ShieldDecision.VETOED,
                violated_invariants=["MAX_RED_STARVATION"],
                audit_message=(
                    f"VETOED {proposal.action_type} on {active}: opposing red wait "
                    f"{j_state.opposing_red_wait_s:.1f}s exceeded "
                    f"{self.config.max_cross_street_red_s:.1f}s; initiating "
                    f"{yellow_phase} toward {starved_phase}."
                ),
            )
            return self._record_command(j_state, cmd)

        # 3. Illegal Direct Jump (CONFLICT_MUTEX / MANDATORY_CLEARANCE)
        if proposal.target_phase == _OPPOSING_GREEN[active]:
            if state.phase_elapsed_s < self.config.min_green_s:
                remaining_min = self.config.min_green_s - state.phase_elapsed_s
                cmd = self._build_command(
                    state=state,
                    proposal=proposal,
                    approved_phase=active,
                    approved_duration_s=remaining_min,
                    decision=ShieldDecision.VETOED,
                    violated_invariants=["MIN_GREEN_LOCK", "CONFLICT_MUTEX"],
                    audit_message=(
                        f"VETOED illegal direct jump {active} -> "
                        f"{proposal.target_phase} at {state.phase_elapsed_s:.1f}s "
                        f"(< min_green {self.config.min_green_s:.1f}s)."
                    ),
                )
                return self._record_command(j_state, cmd)

            yellow_phase = _GREEN_TO_YELLOW[active]
            j_state.pending_target_phase = proposal.target_phase
            cmd = self._build_command(
                state=state,
                proposal=proposal,
                approved_phase=yellow_phase,
                approved_duration_s=self.config.yellow_duration_s,
                decision=ShieldDecision.CLIPPED,
                violated_invariants=["MANDATORY_CLEARANCE"],
                audit_message=(
                    f"CLIPPED direct jump {active} -> {proposal.target_phase}: "
                    f"initiating mandatory clearance {yellow_phase} "
                    f"({self.config.yellow_duration_s:.1f}s)."
                ),
            )
            return self._record_command(j_state, cmd)

        # Reject other non-adjacent clearance jumps directly from green.
        legal_yellow = _GREEN_TO_YELLOW[active]
        if proposal.target_phase not in (active, legal_yellow):
            invariants = (
                ["MIN_GREEN_LOCK", "CONFLICT_MUTEX"]
                if state.phase_elapsed_s < self.config.min_green_s
                else ["CONFLICT_MUTEX"]
            )
            cmd = self._build_command(
                state=state,
                proposal=proposal,
                approved_phase=active,
                approved_duration_s=max(
                    0.0, self.config.min_green_s - state.phase_elapsed_s
                ),
                decision=ShieldDecision.VETOED,
                violated_invariants=invariants,
                audit_message=(
                    f"VETOED illegal phase transition {active} -> "
                    f"{proposal.target_phase}."
                ),
            )
            return self._record_command(j_state, cmd)

        # 4. Minimum Green Lock (MIN_GREEN_LOCK)
        if state.phase_elapsed_s < self.config.min_green_s and (
            proposal.action_type == ControlActionType.RED_TRUNCATION
            or proposal.target_phase != active
        ):
            remaining_min = self.config.min_green_s - state.phase_elapsed_s
            cmd = self._build_command(
                state=state,
                proposal=proposal,
                approved_phase=active,
                approved_duration_s=remaining_min,
                decision=ShieldDecision.VETOED,
                violated_invariants=["MIN_GREEN_LOCK"],
                audit_message=(
                    f"VETOED {proposal.action_type} on {active} at "
                    f"{state.phase_elapsed_s:.1f}s (< min_green "
                    f"{self.config.min_green_s:.1f}s)."
                ),
            )
            return self._record_command(j_state, cmd)

        # Explicit legal transition to the adjacent yellow phase after min_green_s.
        if proposal.target_phase == legal_yellow:
            j_state.pending_target_phase = _OPPOSING_GREEN[active]
            cmd = self._build_command(
                state=state,
                proposal=proposal,
                approved_phase=legal_yellow,
                approved_duration_s=self.config.yellow_duration_s,
                decision=ShieldDecision.APPROVED,
                violated_invariants=[],
                audit_message=(
                    f"APPROVED legal clearance transition {active} -> "
                    f"{legal_yellow} ({self.config.yellow_duration_s:.1f}s)."
                ),
            )
            return self._record_command(j_state, cmd)

        # 5. Duration Clamping (DURATION_BOUNDS)
        clamped_duration = min(
            max(proposal.requested_duration_s, self.config.min_green_s),
            self.config.max_green_s,
        )
        if clamped_duration != proposal.requested_duration_s:
            cmd = self._build_command(
                state=state,
                proposal=proposal,
                approved_phase=active,
                approved_duration_s=clamped_duration,
                decision=ShieldDecision.CLIPPED,
                violated_invariants=["DURATION_BOUNDS"],
                audit_message=(
                    f"CLIPPED {proposal.action_type} duration on {active} from "
                    f"{proposal.requested_duration_s:.1f}s to {clamped_duration:.1f}s "
                    f"(bounds [{self.config.min_green_s:.1f}, "
                    f"{self.config.max_green_s:.1f}])."
                ),
            )
            return self._record_command(j_state, cmd)

        cmd = self._build_command(
            state=state,
            proposal=proposal,
            approved_phase=active,
            approved_duration_s=clamped_duration,
            decision=ShieldDecision.APPROVED,
            violated_invariants=[],
            audit_message=(
                f"APPROVED {proposal.action_type} on {active} for "
                f"{clamped_duration:.1f}s."
            ),
        )
        return self._record_command(j_state, cmd)

    def get_audit_summary(self) -> dict[str, int]:
        """Return counts of APPROVED, CLIPPED, and VETOED decisions in audit_log."""
        counts: dict[str, int] = {
            ShieldDecision.APPROVED.value: 0,
            ShieldDecision.CLIPPED.value: 0,
            ShieldDecision.VETOED.value: 0,
        }
        for entry in self.audit_log:
            counts[entry.shield_decision.value] += 1
        return counts
