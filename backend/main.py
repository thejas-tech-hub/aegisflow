"""AegisFlow FastAPI Gateway & Real-Time WebSocket Engine."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from backend.state_hub import CorridorStateHub, SpeedMultiplier
from backend.vision_service import VisionStreamService
from orchestrator.corridor_physics import ScenarioPreset
from schemas.contracts import (
    JunctionID,
    JunctionStatePacket,
    SpillbackForecast,
    VerifiedSignalCommand,
)

SimControlAction = Literal[
    "start",
    "pause",
    "resume",
    "reset",
    "set_scenario",
    "set_speed",
    "inject_ev",
]


class HealthResponse(BaseModel):
    """Health check response payload."""

    model_config = ConfigDict(extra="forbid")

    status: str
    service: str


class JunctionStateIngestResponse(BaseModel):
    """Response returned after ingesting a JunctionStatePacket."""

    model_config = ConfigDict(extra="forbid")

    forecast: SpillbackForecast
    command: VerifiedSignalCommand


class SimControlRequest(BaseModel):
    """Control command payload for the DualTrackABRunner simulation."""

    model_config = ConfigDict(extra="forbid")

    action: SimControlAction
    scenario: ScenarioPreset | None = None
    speed_multiplier: SpeedMultiplier | None = None


class SimControlResponse(BaseModel):
    """Updated simulation session state after applying a control command."""

    model_config = ConfigDict(extra="forbid")

    status: str
    is_running: bool
    scenario: ScenarioPreset
    speed_multiplier: SpeedMultiplier
    tick: int
    ev_injected_at_ja: bool
    message: str


class VisionSnapshotResponse(BaseModel):
    """Live CCTV + BEV Spatial Occupancy snapshot payload."""

    model_config = ConfigDict(extra="forbid")

    frame_jpeg_b64: str
    packet: JunctionStatePacket
    ev_triggered: bool


class PerceptionTriggerResponse(BaseModel):
    """Response after triggering the 3D corridor race from live CCTV perception."""

    model_config = ConfigDict(extra="forbid")

    status: str
    scenario: ScenarioPreset
    is_running: bool
    forecast: SpillbackForecast
    command: VerifiedSignalCommand


hub = CorridorStateHub()
vision_service = VisionStreamService()
_vision_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Manage CorridorStateHub SQLite connection and WebSocket broadcast loop."""
    await hub.initialize()
    try:
        yield
    finally:
        vision_service.close()
        await hub.close()


app = FastAPI(
    title="AegisFlow Gateway",
    version="0.2.0",
    description="Real-time inter-junction gateway and A/B WebSocket telemetry engine.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return gateway health status."""
    return HealthResponse(status="ok", service="aegisflow-gateway")


@app.post(
    "/api/v1/junctions/{junction_id}/state",
    response_model=JunctionStateIngestResponse,
)
async def ingest_junction_state(
    junction_id: JunctionID,
    packet: JunctionStatePacket,
) -> JunctionStateIngestResponse:
    """Ingest a live JunctionStatePacket and return forecast + verified signal command."""
    if packet.junction_id != junction_id:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Path junction_id '{junction_id.value}' does not match "
                f"packet.junction_id '{packet.junction_id.value}'."
            ),
        )

    forecast, command = await hub.ingest_junction_state(packet)
    return JunctionStateIngestResponse(forecast=forecast, command=command)


@app.post("/api/v1/sim/control", response_model=SimControlResponse)
async def control_simulation(body: SimControlRequest) -> SimControlResponse:
    """Start, pause, reset, switch scenario, change speed, or inject EV alert."""
    action = body.action

    if action in ("start", "resume"):
        await hub.start_simulation(
            scenario=body.scenario,
            speed_multiplier=body.speed_multiplier,
        )
        msg = "Simulation running."
    elif action == "pause":
        await hub.pause_simulation()
        msg = "Simulation paused."
    elif action == "reset":
        await hub.reset_simulation(scenario=body.scenario)
        msg = f"Simulation reset to scenario '{hub.scenario}'."
    elif action == "set_scenario":
        if body.scenario is None:
            raise HTTPException(
                status_code=422,
                detail="Field 'scenario' is required for action 'set_scenario'.",
            )
        await hub.reset_simulation(scenario=body.scenario)
        msg = f"Scenario updated to '{hub.scenario}'."
    elif action == "set_speed":
        if body.speed_multiplier is None:
            raise HTTPException(
                status_code=422,
                detail="Field 'speed_multiplier' is required for action 'set_speed'.",
            )
        await hub.set_speed(body.speed_multiplier)
        msg = f"Broadcast speed set to {hub.speed_multiplier}x."
    elif action == "inject_ev":
        await hub.inject_ev_alert_at_ja()
        msg = "Injected manual/CCTV EV alert approaching J_A."
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

    return SimControlResponse(
        status="ok",
        is_running=hub.is_running,
        scenario=hub.scenario,
        speed_multiplier=hub.speed_multiplier,
        tick=hub.runner.baseline_sim.tick,
        ev_injected_at_ja=hub.ev_injected_at_ja,
        message=msg,
    )


@app.get("/api/v1/sim/benchmark")
async def run_sim_benchmark(
    scenario: Annotated[ScenarioPreset, Query()] = "peak_spillback",
    seed: Annotated[int, Query()] = 42,
    max_ticks: Annotated[int, Query(ge=10, le=500)] = 150,
) -> dict[str, Any]:
    """Run a complete A/B episode and return Baseline EVP vs. AegisFlow KPIs."""
    return hub.run_benchmark(scenario=scenario, seed=seed, max_ticks=max_ticks)


@app.get("/api/v1/perception/snapshot", response_model=VisionSnapshotResponse)
async def get_perception_snapshot() -> VisionSnapshotResponse:
    """Step the roadside perception node by 1 frame and return JPEG + packet."""
    async with _vision_lock:
        snapshot = await asyncio.to_thread(vision_service.step_snapshot)
    return VisionSnapshotResponse(
        frame_jpeg_b64=snapshot.frame_jpeg_b64,
        packet=snapshot.packet,
        ev_triggered=snapshot.ev_triggered,
    )


@app.post(
    "/api/v1/perception/trigger-corridor",
    response_model=PerceptionTriggerResponse,
)
async def trigger_corridor_from_perception() -> PerceptionTriggerResponse:
    """Ingest latest CCTV packet and launch the peak_spillback emergency race."""
    async with _vision_lock:
        packet = await asyncio.to_thread(vision_service.get_latest_or_step_packet)

    await hub.reset_simulation(scenario="peak_spillback")
    await hub.inject_ev_alert_at_ja()
    forecast, command = await hub.ingest_junction_state(packet)
    await hub.start_simulation(scenario="peak_spillback")

    return PerceptionTriggerResponse(
        status="ok",
        scenario=hub.scenario,
        is_running=hub.is_running,
        forecast=forecast,
        command=command,
    )


@app.websocket("/ws/corridor")
async def corridor_websocket(websocket: WebSocket) -> None:
    """Stream live ABFrameSnapshot JSON frames to connected dashboard clients."""
    await hub.register_client(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.unregister_client(websocket)
