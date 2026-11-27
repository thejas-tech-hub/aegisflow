"""Async corridor state hub, simulation manager, and SQLite audit logger."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import aiosqlite
from fastapi import WebSocket, WebSocketDisconnect

from orchestrator.ab_runner import DualTrackABRunner
from orchestrator.controller import AegisFlowController
from orchestrator.corridor_physics import ScenarioPreset
from schemas.contracts import (
    JunctionID,
    JunctionStatePacket,
    SpillbackForecast,
    VerifiedSignalCommand,
)

SpeedMultiplier = Literal[1, 2, 4]
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "telemetry.db"
logger = logging.getLogger(__name__)


class CorridorStateHub:
    """Manages live telemetry, DualTrackABRunner simulation, WebSockets, and SQLite audit logs."""

    def __init__(
        self,
        db_path: Path | str = DEFAULT_DB_PATH,
        scenario: ScenarioPreset = "peak_spillback",
        seed: int = 42,
    ) -> None:
        """Initialize the state hub, simulation runner, and rolling frame buffer."""
        self.db_path = Path(db_path)
        self.scenario: ScenarioPreset = scenario
        self.seed = seed
        self.speed_multiplier: SpeedMultiplier = 1
        self.is_running: bool = False
        self.ev_injected_at_ja: bool = False

        self.runner = DualTrackABRunner(scenario=scenario, seed=seed)
        self.live_controller = AegisFlowController()

        self.latest_states: dict[JunctionID, JunctionStatePacket] = {}
        self.latest_forecasts: dict[JunctionID, SpillbackForecast] = {}
        self.latest_commands: dict[JunctionID, VerifiedSignalCommand] = {}
        self.frame_history: deque[dict[str, Any]] = deque(maxlen=200)

        self._clients: set[WebSocket] = set()
        self._db: aiosqlite.Connection | None = None
        self._db_lock = asyncio.Lock()
        self._sim_lock = asyncio.Lock()
        self._broadcast_task: asyncio.Task[None] | None = None

    @property
    def broadcast_interval_s(self) -> float:
        """Return broadcast interval in seconds (1000ms at 1x, 500ms at 2x, 250ms at 4x)."""
        return 1.0 / float(self.speed_multiplier)

    async def initialize(self) -> None:
        """Initialize SQLite telemetry database and start background broadcast loop."""
        await self._ensure_db()
        if self._broadcast_task is None or self._broadcast_task.done():
            self._broadcast_task = asyncio.create_task(self._broadcast_loop())

    async def close(self) -> None:
        """Cancel background broadcast loop and close SQLite connection."""
        if self._broadcast_task is not None and not self._broadcast_task.done():
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
            self._broadcast_task = None

        async with self._db_lock:
            if self._db is not None:
                await self._db.close()
                self._db = None

    async def _ensure_db(self) -> aiosqlite.Connection:
        """Open SQLite connection lazily and ensure audit table exists."""
        async with self._db_lock:
            if self._db is None:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self._db = await aiosqlite.connect(self.db_path)
                await self._db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS shield_audit_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT NOT NULL,
                        track TEXT NOT NULL,
                        source TEXT NOT NULL,
                        junction_id TEXT NOT NULL,
                        sim_timestamp REAL NOT NULL,
                        approved_phase TEXT NOT NULL,
                        approved_duration_s REAL NOT NULL,
                        shield_decision TEXT NOT NULL,
                        original_action_type TEXT NOT NULL,
                        violated_invariants TEXT NOT NULL,
                        audit_message TEXT NOT NULL
                    )
                    """
                )
                await self._db.commit()
            return self._db

    async def _log_shield_audit_event(
        self,
        *,
        track: str,
        source: str,
        command: VerifiedSignalCommand,
    ) -> None:
        """Persist a Safety Shield verification event to SQLite."""
        db = await self._ensure_db()
        async with self._db_lock:
            await db.execute(
                """
                INSERT INTO shield_audit_events (
                    created_at,
                    track,
                    source,
                    junction_id,
                    sim_timestamp,
                    approved_phase,
                    approved_duration_s,
                    shield_decision,
                    original_action_type,
                    violated_invariants,
                    audit_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(UTC).isoformat(),
                    track,
                    source,
                    command.junction_id.value,
                    command.timestamp,
                    command.approved_phase.value,
                    command.approved_duration_s,
                    command.shield_decision.value,
                    command.original_action_type.value,
                    json.dumps(command.violated_invariants),
                    command.audit_message,
                ),
            )
            await db.commit()

    async def get_audit_event_count(self) -> int:
        """Return total number of persisted Safety Shield audit events."""
        db = await self._ensure_db()
        async with (
            self._db_lock,
            db.execute("SELECT COUNT(*) FROM shield_audit_events") as cursor,
        ):
            row = await cursor.fetchone()
            return int(row[0]) if row else 0

    async def ingest_junction_state(
        self,
        packet: JunctionStatePacket,
    ) -> tuple[SpillbackForecast, VerifiedSignalCommand]:
        """Store live JunctionStatePacket, run pipeline, and log Safety Shield audit."""
        self.latest_states[packet.junction_id] = packet

        # Fill any missing corridor junctions from the active simulation context.
        sim_states = self.runner.aegisflow_sim.get_state_packets()
        corridor_states: dict[JunctionID, JunctionStatePacket] = {
            jid: self.latest_states.get(jid, sim_states[jid])
            for jid in JunctionID
        }

        forecasts, _, commands = self.live_controller.step(corridor_states)
        forecast = forecasts[packet.junction_id]
        command = commands[packet.junction_id]

        self.latest_forecasts[packet.junction_id] = forecast
        self.latest_commands[packet.junction_id] = command

        await self._log_shield_audit_event(
            track="live_ingest",
            source=packet.source,
            command=command,
        )
        return forecast, command

    async def step_simulation(self) -> dict[str, Any]:
        """Advance DualTrackABRunner by one tick, buffer snapshot, and log audit events."""
        async with self._sim_lock:
            snapshot = self.runner.step()
            self.frame_history.append(snapshot)

        aegis_commands = snapshot["aegisflow"]["commands"]
        for cmd_dict in aegis_commands.values():
            cmd = VerifiedSignalCommand.model_validate(cmd_dict)
            await self._log_shield_audit_event(
                track="aegisflow_sim",
                source="sumo",
                command=cmd,
            )
        return snapshot

    async def get_latest_or_step_snapshot(self) -> dict[str, Any]:
        """Return the latest buffered ABFrameSnapshot, stepping once if buffer is empty."""
        if self.frame_history:
            return self.frame_history[-1]
        return await self.step_simulation()

    async def start_simulation(
        self,
        scenario: ScenarioPreset | None = None,
        speed_multiplier: SpeedMultiplier | None = None,
    ) -> None:
        """Start or resume the live DualTrackABRunner loop."""
        if scenario is not None and scenario != self.scenario:
            await self.reset_simulation(scenario=scenario)
        if speed_multiplier is not None:
            self.speed_multiplier = speed_multiplier
        self.is_running = True

    async def pause_simulation(self) -> None:
        """Pause the live DualTrackABRunner loop."""
        self.is_running = False

    async def reset_simulation(
        self,
        scenario: ScenarioPreset | None = None,
    ) -> None:
        """Reset DualTrackABRunner and clear rolling frame history."""
        async with self._sim_lock:
            if scenario is not None:
                self.scenario = scenario
            self.runner = DualTrackABRunner(scenario=self.scenario, seed=self.seed)
            self.ev_injected_at_ja = False
            self.frame_history.clear()

    async def set_speed(self, speed_multiplier: SpeedMultiplier) -> None:
        """Update broadcast speed multiplier (1x, 2x, or 4x)."""
        self.speed_multiplier = speed_multiplier

    async def inject_ev_alert_at_ja(self) -> None:
        """Inject a manual/CCTV emergency vehicle alert approaching Junction J_A."""
        async with self._sim_lock:
            for sim in (self.runner.baseline_sim, self.runner.aegisflow_sim):
                sim.ev_completed = False
                sim.ev_travel_time_s = None
                sim.ev_speed_mps = 14.0
                sim.ev_position_m = -120.0
            self.ev_injected_at_ja = True

        sim_ja = self.runner.aegisflow_sim.get_state_packets()[JunctionID.J_A]
        cctv_packet = sim_ja.model_copy(
            update={
                "source": "cctv",
                "ev_detected": True,
                "ev_confidence": 0.96,
                "ev_eta_s": 8.5,
                "ev_distance_m": 120.0,
            }
        )
        await self.ingest_junction_state(cctv_packet)

    def run_benchmark(
        self,
        scenario: ScenarioPreset | None = None,
        seed: int | None = None,
        max_ticks: int = 150,
    ) -> dict[str, Any]:
        """Run a complete deterministic episode and return A/B KPI comparison."""
        bench_runner = DualTrackABRunner(
            scenario=scenario or self.scenario,
            seed=self.seed if seed is None else seed,
        )
        return bench_runner.run_full_episode(max_ticks=max_ticks)

    async def register_client(self, websocket: WebSocket) -> None:
        """Register a connected WebSocket client and send an immediate initial frame."""
        await websocket.accept()
        self._clients.add(websocket)
        initial_frame = await self.get_latest_or_step_snapshot()
        await websocket.send_json(initial_frame)

    def unregister_client(self, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket client."""
        self._clients.discard(websocket)

    async def broadcast_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Broadcast an ABFrameSnapshot JSON payload to all connected WebSocket clients."""
        if not self._clients:
            return
        stale: list[WebSocket] = []
        for client in list(self._clients):
            try:
                await client.send_json(snapshot)
            except (WebSocketDisconnect, RuntimeError, OSError):
                stale.append(client)
        for client in stale:
            self._clients.discard(client)

    async def _broadcast_loop(self) -> None:
        """Periodically step the active simulation and broadcast frames."""
        while True:
            try:
                await asyncio.sleep(self.broadcast_interval_s)
                if not self.is_running:
                    continue
                snapshot = await self.step_simulation()
                await self.broadcast_snapshot(snapshot)
            except asyncio.CancelledError:
                raise
            except (RuntimeError, OSError, ValueError) as exc:
                logger.warning("Broadcast loop transient error: %s", exc)
