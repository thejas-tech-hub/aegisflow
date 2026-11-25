"""Unit and integration tests for the physics-informed SpillbackPredictor."""

from predictor import PredictorConfig, SpillbackPredictor
from schemas.contracts import (
    JunctionID,
    JunctionStatePacket,
    SignalPhase,
    SpillbackForecast,
    VehicleMix,
)
from schemas.mock_generator import MockCorridorGenerator


def _make_packet(
    junction_id: JunctionID,
    timestamp: float = 10.0,
    active_phase: SignalPhase = SignalPhase.NS_GREEN,
    phase_elapsed_s: float = 5.0,
    queue_length_m: float = 90.0,
    link_length_m: float = 300.0,
    avg_speed_mps: float = 9.0,
    inflow_rate_vps: float = 0.45,
    outflow_rate_vps: float = 0.45,
    ev_detected: bool = False,
    ev_confidence: float = 0.0,
    ev_eta_s: float | None = None,
    ev_distance_m: float | None = None,
) -> JunctionStatePacket:
    """Construct a valid JunctionStatePacket fixture for predictor tests."""
    occupancy = min(1.0, max(0.0, queue_length_m / link_length_m))
    return JunctionStatePacket(
        junction_id=junction_id,
        timestamp=timestamp,
        source="sumo",
        active_phase=active_phase,
        phase_elapsed_s=phase_elapsed_s,
        spatial_occupancy_ratio=occupancy,
        pcu_density=12.0,
        queue_length_m=queue_length_m,
        link_length_m=link_length_m,
        avg_speed_mps=avg_speed_mps,
        inflow_rate_vps=inflow_rate_vps,
        outflow_rate_vps=outflow_rate_vps,
        vehicle_mix=VehicleMix(
            motorcycles=8,
            auto_rickshaws=4,
            cars=6,
            buses_trucks=2,
            emergency_vehicles=1 if ev_detected else 0,
        ),
        ev_detected=ev_detected,
        ev_confidence=ev_confidence,
        ev_eta_s=ev_eta_s,
        ev_distance_m=ev_distance_m,
    )


def _make_corridor(
    *,
    ja_outflow: float = 0.35,
    jb_phase: SignalPhase = SignalPhase.NS_GREEN,
    jb_queue_m: float = 90.0,
    jb_inflow: float = 0.45,
    ja_ev: bool = False,
) -> dict[JunctionID, JunctionStatePacket]:
    """Create a synchronized 3-junction corridor snapshot."""
    return {
        JunctionID.J_A: _make_packet(
            JunctionID.J_A,
            active_phase=SignalPhase.EW_GREEN,
            outflow_rate_vps=ja_outflow,
            avg_speed_mps=10.0,
            ev_detected=ja_ev,
            ev_confidence=0.95 if ja_ev else 0.0,
            ev_eta_s=12.0 if ja_ev else None,
            ev_distance_m=150.0 if ja_ev else None,
        ),
        JunctionID.J_B: _make_packet(
            JunctionID.J_B,
            active_phase=jb_phase,
            phase_elapsed_s=5.0,
            queue_length_m=jb_queue_m,
            inflow_rate_vps=jb_inflow,
        ),
        JunctionID.J_C: _make_packet(
            JunctionID.J_C,
            active_phase=SignalPhase.NS_GREEN,
            queue_length_m=60.0,
        ),
    }


def test_upstream_surge_at_ja_increases_downstream_jb_risk() -> None:
    """High outflow at J_A increases predicted queue and risk index at J_B."""
    predictor = SpillbackPredictor(PredictorConfig(default_horizon_s=45))

    baseline_corridor = _make_corridor(ja_outflow=0.25, jb_queue_m=100.0)
    surge_corridor = _make_corridor(ja_outflow=1.60, jb_queue_m=100.0)

    baseline_forecast = predictor.predict_junction(
        JunctionID.J_B, baseline_corridor, horizon_s=45
    )
    surge_predictor = SpillbackPredictor(PredictorConfig(default_horizon_s=45))
    surge_forecast = surge_predictor.predict_junction(
        JunctionID.J_B, surge_corridor, horizon_s=45
    )

    assert surge_forecast.predicted_queue_length_m > baseline_forecast.predicted_queue_length_m
    assert surge_forecast.spillback_risk_index > baseline_forecast.spillback_risk_index


def test_active_ew_green_discharge_reduces_jb_queue_vs_ns_green() -> None:
    """EW_GREEN arterial discharge yields shorter predicted queue than NS_GREEN."""
    corridor_red = _make_corridor(
        jb_phase=SignalPhase.NS_GREEN, jb_queue_m=140.0, ja_outflow=0.45
    )
    corridor_green = _make_corridor(
        jb_phase=SignalPhase.EW_GREEN, jb_queue_m=140.0, ja_outflow=0.45
    )

    pred_red = SpillbackPredictor().predict_junction(JunctionID.J_B, corridor_red)
    pred_green = SpillbackPredictor().predict_junction(JunctionID.J_B, corridor_green)

    assert pred_green.predicted_queue_length_m < pred_red.predicted_queue_length_m


def test_high_congestion_with_platoon_triggers_spillback_imminent() -> None:
    """220m queue on 300m link plus incoming platoon triggers spillback_imminent."""
    predictor = SpillbackPredictor()
    congested = _make_corridor(
        ja_outflow=1.1,
        jb_phase=SignalPhase.NS_GREEN,
        jb_queue_m=220.0,
        jb_inflow=0.95,
    )

    forecast = predictor.predict_junction(JunctionID.J_B, congested, horizon_s=45)

    assert forecast.spillback_risk_index >= predictor.config.spillback_threshold
    assert forecast.spillback_imminent is True


def test_ev_at_ja_propagates_valid_eta_to_jb_and_jc() -> None:
    """EV detected at J_A propagates valid, monotonically increasing ETA downstream."""
    predictor = SpillbackPredictor()
    corridor = _make_corridor(ja_ev=True)

    forecasts = predictor.predict_corridor(corridor)

    eta_a = forecasts[JunctionID.J_A].predicted_ev_eta_s
    eta_b = forecasts[JunctionID.J_B].predicted_ev_eta_s
    eta_c = forecasts[JunctionID.J_C].predicted_ev_eta_s

    assert eta_a is not None and eta_a > 0.0
    assert eta_b is not None and eta_b > eta_a
    assert eta_c is not None and eta_c > eta_b


def test_residual_calibration_hook_adapts_bias_on_feedback() -> None:
    """ResidualCalibrationHook updates junction bias from observed queue feedback."""
    predictor = SpillbackPredictor()
    t0_corridor = _make_corridor(jb_queue_m=100.0)
    forecast = predictor.predict_corridor(t0_corridor, horizon_s=45)[JunctionID.J_B]

    # Observed queue at t=45s exceeds predicted queue by 25m.
    observed_q = min(400.0, forecast.predicted_queue_length_m + 25.0)
    t45_corridor = {
        jid: pkt.model_copy(
            update={
                "timestamp": 55.0,
                "queue_length_m": observed_q if jid == JunctionID.J_B else pkt.queue_length_m,
            }
        )
        for jid, pkt in t0_corridor.items()
    }
    biases = predictor.update_calibration(t45_corridor)

    assert biases[JunctionID.J_B] > 0.0
    assert predictor.calibration.update_counts[JunctionID.J_B] == 1


def test_mock_corridor_120_tick_smoke_test() -> None:
    """Run 120 ticks of MockCorridorGenerator through SpillbackPredictor cleanly."""
    predictor = SpillbackPredictor()
    generator = MockCorridorGenerator(seed=42)

    total_forecasts = 0
    jb_spillback_seen = False

    for frame in generator:
        predictor.update_calibration(frame)
        forecasts = predictor.predict_corridor(frame)
        assert set(forecasts.keys()) == {
            JunctionID.J_A,
            JunctionID.J_B,
            JunctionID.J_C,
        }
        for jid, forecast in forecasts.items():
            assert isinstance(forecast, SpillbackForecast)
            assert forecast.junction_id == jid
            if jid == JunctionID.J_B and forecast.spillback_imminent:
                jb_spillback_seen = True
            total_forecasts += 1

    assert total_forecasts == 360
    assert jb_spillback_seen is True
