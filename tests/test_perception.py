"""Unit tests for BEVSpatialMapper and RoadsidePerceptionNode."""

import pytest

from perception.detector import RoadsidePerceptionNode
from perception.spatial import BEVSpatialMapper, BEVVehicle
from schemas.contracts import JunctionID, JunctionStatePacket


def test_homography_maps_pixel_corners_to_exact_bev_corners() -> None:
    """Known src_pixel_points must project to exact dst_meter_points."""
    mapper = BEVSpatialMapper()

    for src_pt, dst_pt in zip(
        mapper.src_pixel_points,
        mapper.dst_meter_points,
        strict=True,
    ):
        x_m, y_m = mapper.pixel_to_bev(float(src_pt[0]), float(src_pt[1]))
        assert x_m == pytest.approx(float(dst_pt[0]), abs=1e-3)
        assert y_m == pytest.approx(float(dst_pt[1]), abs=1e-3)


def test_spatial_occupancy_ratio_strictly_clamped_zero_to_one() -> None:
    """spatial_occupancy_ratio must remain in [0.0, 1.0] even under extreme load."""
    mapper = BEVSpatialMapper()

    empty_metrics = mapper.compute_metrics([])
    assert empty_metrics.spatial_occupancy_ratio == 0.0

    # 30 buses (30 * 27.5 = 825 m^2 > 350 m^2 road area) must clamp to 1.0
    overloaded = [
        BEVVehicle(
            track_id=idx,
            vehicle_class="bus",
            x_m=3.5,
            y_m=float((idx % 45) + 1),
            speed_mps=1.0,
        )
        for idx in range(30)
    ]
    saturated_metrics = mapper.compute_metrics(overloaded)
    assert 0.0 <= saturated_metrics.spatial_occupancy_ratio <= 1.0
    assert saturated_metrics.spatial_occupancy_ratio == 1.0


def test_synthetic_frame_emits_valid_packet_and_bev_minimap() -> None:
    """Synthetic frame processing emits a valid JunctionStatePacket and BEV mini-map."""
    node = RoadsidePerceptionNode(
        junction_id=JunctionID.J_A,
        demo_synthetic=True,
        fps=10.0,
    )
    try:
        packets = node.run_synthetic_stream(max_frames=12, show=False, emit_interval_s=1.0)
        assert len(packets) >= 2
        for pkt in packets:
            validated = JunctionStatePacket.model_validate(pkt.model_dump())
            assert validated.source == "cctv"
            assert validated.junction_id == JunctionID.J_A
            assert 0.0 <= validated.spatial_occupancy_ratio <= 1.0
            assert validated.ev_detected is True

        frame, detections, classes = node.generate_synthetic_frame(frame_idx=5)
        pkt, composite = node.process_frame(
            frame=frame,
            timestamp_s=0.5,
            frame_idx=5,
            precomputed_detections=(detections, classes),
        )
        assert isinstance(pkt, JunctionStatePacket)
        # Side-by-side composite: 1280px CCTV + 360px BEV = 1640px wide, 720px tall
        assert composite.shape == (720, 1640, 3)
        assert composite.sum() > 0
    finally:
        node.close()
