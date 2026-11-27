"""FastAPI TestClient tests for AegisFlow backend gateway and WebSocket engine."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app, hub
from schemas.contracts import (
    JunctionID,
    JunctionStatePacket,
    SignalPhase,
    SpillbackForecast,
    VehicleMix,
    VerifiedSignalCommand,
)


def _sample_j_a_packet() -> JunctionStatePacket:
    """Create a valid JunctionStatePacket for Junction J_A."""
    return JunctionStatePacket(
        junction_id=JunctionID.J_A,
        timestamp=12.0,
        source="cctv",
        active_phase=SignalPhase.NS_GREEN,
        phase_elapsed_s=15.0,
        spatial_occupancy_ratio=0.45,
        pcu_density=18.5,
        queue_length_m=62.0,
        link_length_m=300.0,
        avg_speed_mps=8.2,
        inflow_rate_vps=0.5,
        outflow_rate_vps=1.1,
        vehicle_mix=VehicleMix(
            motorcycles=10,
            auto_rickshaws=5,
            cars=8,
            buses_trucks=2,
            emergency_vehicles=1,
        ),
        ev_detected=True,
        ev_confidence=0.95,
        ev_eta_s=9.0,
        ev_distance_m=110.0,
    )


def test_health_endpoint() -> None:
    """GET /api/v1/health returns status ok and service name."""
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "aegisflow-gateway"}


def test_ingest_junction_j_a_state(tmp_path: Path) -> None:
    """POST /api/v1/junctions/J_A/state validates packet and returns forecast + command."""
    original_db = hub.db_path
    hub.db_path = tmp_path / "test_telemetry.db"
    try:
        packet = _sample_j_a_packet()
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/junctions/J_A/state",
                json=packet.model_dump(mode="json"),
            )

        assert response.status_code == 200
        payload = response.json()
        forecast = SpillbackForecast.model_validate(payload["forecast"])
        command = VerifiedSignalCommand.model_validate(payload["command"])

        assert forecast.junction_id == JunctionID.J_A
        assert command.junction_id == JunctionID.J_A
        assert hub.latest_states[JunctionID.J_A] == packet
        assert hub.db_path.exists()
    finally:
        hub.db_path = original_db


def test_sim_control_and_benchmark_endpoints(tmp_path: Path) -> None:
    """POST /api/v1/sim/control and GET /api/v1/sim/benchmark return valid payloads."""
    original_db = hub.db_path
    hub.db_path = tmp_path / "test_telemetry.db"
    try:
        with TestClient(app) as client:
            ctrl_resp = client.post(
                "/api/v1/sim/control",
                json={"action": "set_speed", "speed_multiplier": 4},
            )
            assert ctrl_resp.status_code == 200
            assert ctrl_resp.json()["speed_multiplier"] == 4

            ev_resp = client.post(
                "/api/v1/sim/control",
                json={"action": "inject_ev"},
            )
            assert ev_resp.status_code == 200
            assert ev_resp.json()["ev_injected_at_ja"] is True

            bench_resp = client.get("/api/v1/sim/benchmark")
            assert bench_resp.status_code == 200
            bench = bench_resp.json()

        assert bench["scenario"] == "peak_spillback"
        assert "baseline_kpis" in bench
        assert "aegisflow_kpis" in bench
        assert "comparison_kpis" in bench
        assert bench["comparison_kpis"]["ev_travel_time_reduction_pct"] > 0.0
    finally:
        hub.db_path = original_db


def test_corridor_websocket_streams_valid_ab_snapshot(tmp_path: Path) -> None:
    """WS /ws/corridor connects and emits valid ABFrameSnapshot JSON frames."""
    original_db = hub.db_path
    hub.db_path = tmp_path / "test_telemetry.db"
    try:
        with (
            TestClient(app) as client,
            client.websocket_connect("/ws/corridor") as websocket,
        ):
            frame = websocket.receive_json()

        assert isinstance(frame, dict)
        assert "tick" in frame
        assert "scenario" in frame
        assert "baseline" in frame
        assert "aegisflow" in frame
        assert "comparison_kpis" in frame
        assert "J_A" in frame["aegisflow"]["states"]
        assert "J_B" in frame["aegisflow"]["states"]
        assert "J_C" in frame["aegisflow"]["states"]
    finally:
        hub.db_path = original_db
