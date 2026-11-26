"""AegisFlow FastAPI Gateway application."""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health check response payload."""

    status: str
    service: str


app = FastAPI(
    title="AegisFlow Gateway",
    version="0.1.0",
    description="Real-time traffic operations command center gateway.",
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


@app.websocket("/ws/corridor")
async def corridor_websocket(websocket: WebSocket) -> None:
    """Placeholder WebSocket endpoint for corridor telemetry streaming."""
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_text()
            await websocket.send_text(f"ack: {message}")
    except WebSocketDisconnect:
        return
