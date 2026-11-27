"""Roadside YOLOv11n + ByteTrack perception node and BEV side-by-side visualizer."""

from __future__ import annotations

import argparse
import logging
import math
import time
from pathlib import Path
from typing import Any

import cv2
import httpx
import numpy as np
import supervision as sv

from perception.spatial import (
    DEFAULT_CALIBRATION_PATH,
    BEVSpatialMapper,
    BEVVehicle,
    VehicleClass,
)
from schemas.contracts import (
    JunctionID,
    JunctionStatePacket,
    SignalPhase,
)

logger = logging.getLogger(__name__)

_YOLO_COCO_TO_CLASS: dict[int, VehicleClass] = {
    1: "motorcycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

_SYNTHETIC_CLASS_IDS: dict[VehicleClass, int] = {
    "motorcycle": 3,
    "auto_rickshaw": 80,
    "car": 2,
    "bus": 5,
    "truck": 7,
    "ambulance": 81,
}


class _FallbackByteTrack:
    """Lightweight IoU/centroid tracker used when supervision lacks sv.ByteTrack."""

    def __init__(self) -> None:
        """Initialize track counter and previous box centers."""
        self._next_id = 1
        self._prev_tracks: dict[int, tuple[float, float]] = {}

    def update_with_detections(self, detections: sv.Detections) -> sv.Detections:
        """Assign persistent tracker_id values to sv.Detections."""
        if len(detections) == 0:
            detections.tracker_id = np.empty((0,), dtype=int)
            return detections

        assigned: list[int] = []
        new_prev: dict[int, tuple[float, float]] = {}
        used_ids: set[int] = set()

        for box in detections.xyxy:
            cx = float((box[0] + box[2]) / 2.0)
            cy = float((box[1] + box[3]) / 2.0)
            best_id: int | None = None
            best_dist = 120.0

            for tid, (px, py) in self._prev_tracks.items():
                if tid in used_ids:
                    continue
                dist = math.hypot(cx - px, cy - py)
                if dist < best_dist:
                    best_dist = dist
                    best_id = tid

            if best_id is None:
                best_id = self._next_id
                self._next_id += 1

            used_ids.add(best_id)
            assigned.append(best_id)
            new_prev[best_id] = (cx, cy)

        self._prev_tracks = new_prev
        detections.tracker_id = np.array(assigned, dtype=int)
        return detections


class RoadsidePerceptionNode:
    """Detects and tracks heterogeneous Indian traffic, projects to BEV, and emits packets."""

    def __init__(
        self,
        junction_id: JunctionID = JunctionID.J_A,
        calibration_path: Path | str = DEFAULT_CALIBRATION_PATH,
        model_path: str = "yolo11n.pt",
        fps: float = 10.0,
        demo_synthetic: bool = False,
        api_url: str | None = None,
    ) -> None:
        """Initialize BEV spatial mapper, ByteTrack tracker, and optional HTTP client."""
        self.junction_id = junction_id
        self.model_path = model_path
        self.fps = max(1.0, fps)
        self.demo_synthetic = demo_synthetic
        self.api_url = api_url.rstrip("/") if api_url else None

        self.mapper = BEVSpatialMapper(calibration_path=calibration_path)
        self.inv_homography: np.ndarray = np.linalg.inv(self.mapper.homography_matrix)
        byte_track_cls = getattr(sv, "ByteTrack", None)
        self.tracker: Any = (
            byte_track_cls(frame_rate=round(self.fps))
            if byte_track_cls is not None
            else _FallbackByteTrack()
        )

        self._model: Any | None = None
        self._prev_bev_pose: dict[int, tuple[float, float, float]] = {}
        self._smoothed_speed: dict[int, float] = {}
        self._http_client: httpx.Client | None = (
            httpx.Client(timeout=2.0) if self.api_url else None
        )

    def close(self) -> None:
        """Release HTTP client resources."""
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def _get_model(self) -> Any:
        """Lazily load Ultralytics YOLOv11n only when running real frame inference."""
        if self._model is None:
            from ultralytics import YOLO

            self._model = YOLO(self.model_path)
        return self._model

    def _bev_to_pixel(self, x_m: float, y_m: float) -> tuple[float, float]:
        """Project metric BEV (X, Y) back to oblique CCTV pixel (u, v)."""
        pts = np.array([[[x_m, y_m]]], dtype=np.float32)
        projected = cv2.perspectiveTransform(pts, self.inv_homography)
        return float(projected[0, 0, 0]), float(projected[0, 0, 1])

    def generate_synthetic_frame(
        self,
        frame_idx: int,
        width: int = 1280,
        height: int = 720,
    ) -> tuple[np.ndarray, sv.Detections, list[VehicleClass]]:
        """Generate a realistic synthetic oblique CCTV frame with an approaching ambulance."""
        frame = np.full((height, width, 3), (28, 32, 38), dtype=np.uint8)

        # Draw oblique road polygon from calibration_config.json src_pixel_points
        roi_pts = self.mapper.src_pixel_points.astype(np.int32)
        cv2.fillPoly(frame, [roi_pts], (52, 56, 62))
        cv2.polylines(frame, [roi_pts], isClosed=True, color=(80, 200, 255), thickness=2)

        # Draw center dashed lane divider
        for y_m in range(2, 49, 4):
            p1 = self._bev_to_pixel(self.mapper.corridor_width_m / 2.0, float(y_m))
            p2 = self._bev_to_pixel(self.mapper.corridor_width_m / 2.0, float(y_m + 2))
            cv2.line(
                frame,
                (int(p1[0]), int(p1[1])),
                (int(p2[0]), int(p2[1])),
                (200, 200, 200),
                2,
            )

        t_s = frame_idx / self.fps
        # Deterministic heterogeneous Indian traffic stream moving toward Y=0
        actors: list[tuple[VehicleClass, float, float, float]] = [
            ("bus", 1.8, (14.0 - 1.2 * t_s) % 44.0 + 3.0, 1.2),
            ("car", 5.2, (22.0 - 2.0 * t_s) % 44.0 + 3.0, 2.0),
            ("auto_rickshaw", 2.4, (28.0 - 3.2 * t_s) % 44.0 + 3.0, 3.2),
            ("motorcycle", 4.1, (19.0 - 4.5 * t_s) % 44.0 + 3.0, 4.5),
            ("motorcycle", 6.0, (34.0 - 4.0 * t_s) % 44.0 + 3.0, 4.0),
            # Approaching ambulance moving briskly down the right lane
            ("ambulance", 5.1, max(3.5, 45.0 - 7.5 * (t_s % 6.0)), 7.5),
        ]

        boxes: list[list[float]] = []
        class_ids: list[int] = []
        confidences: list[float] = []
        vehicle_classes: list[VehicleClass] = []

        for v_class, x_m, y_m, _speed in actors:
            u, v = self._bev_to_pixel(x_m, y_m)
            # Perspective-scaled box size (larger closer to camera at lower Y)
            scale = max(0.35, 1.15 - (y_m / self.mapper.corridor_length_m) * 0.7)
            box_w = {
                "motorcycle": 34,
                "auto_rickshaw": 56,
                "car": 78,
                "bus": 110,
                "truck": 105,
                "ambulance": 84,
            }[v_class] * scale
            box_h = {
                "motorcycle": 48,
                "auto_rickshaw": 64,
                "car": 62,
                "bus": 105,
                "truck": 96,
                "ambulance": 72,
            }[v_class] * scale

            x1 = max(0.0, u - box_w / 2.0)
            y1 = max(0.0, v - box_h)
            x2 = min(float(width - 1), u + box_w / 2.0)
            y2 = min(float(height - 1), v)

            body_color = {
                "motorcycle": (240, 190, 40),
                "auto_rickshaw": (30, 195, 255),
                "car": (210, 140, 70),
                "bus": (190, 95, 165),
                "truck": (160, 90, 130),
                "ambulance": (245, 245, 250),
            }[v_class]
            cv2.rectangle(
                frame,
                (int(x1), int(y1)),
                (int(x2), int(y2)),
                body_color,
                thickness=-1,
            )
            if v_class == "ambulance":
                beacon_color = (0, 0, 255) if (frame_idx // 2) % 2 == 0 else (255, 80, 0)
                cv2.circle(
                    frame,
                    (int((x1 + x2) / 2.0), int(y1 + 6)),
                    max(4, int(6 * scale)),
                    beacon_color,
                    thickness=-1,
                )

            boxes.append([x1, y1, x2, y2])
            class_ids.append(_SYNTHETIC_CLASS_IDS[v_class])
            confidences.append(0.95 if v_class == "ambulance" else 0.90)
            vehicle_classes.append(v_class)

        detections = sv.Detections(
            xyxy=np.array(boxes, dtype=np.float32),
            confidence=np.array(confidences, dtype=np.float32),
            class_id=np.array(class_ids, dtype=int),
        )
        return frame, detections, vehicle_classes

    def _detect_with_yolo(
        self,
        frame: np.ndarray,
    ) -> tuple[sv.Detections, list[VehicleClass]]:
        """Run YOLOv11n inference and filter to road vehicle classes."""
        model = self._get_model()
        results = model(frame, verbose=False)[0]
        detections = sv.Detections.from_ultralytics(results)

        if detections.class_id is None or len(detections) == 0:
            return sv.Detections.empty(), []

        keep_mask = np.isin(detections.class_id, list(_YOLO_COCO_TO_CLASS.keys()))
        filtered = detections[keep_mask]
        if filtered.class_id is None or len(filtered) == 0:
            return sv.Detections.empty(), []

        classes = [
            _YOLO_COCO_TO_CLASS.get(int(cid), "car") for cid in filtered.class_id
        ]
        return filtered, classes

    def _estimate_speed_mps(
        self,
        track_id: int | None,
        x_m: float,
        y_m: float,
        timestamp_s: float,
    ) -> float:
        """Estimate vehicle speed (m/s) from consecutive BEV coordinates."""
        if track_id is None:
            return 0.0

        prev = self._prev_bev_pose.get(track_id)
        self._prev_bev_pose[track_id] = (x_m, y_m, timestamp_s)
        if prev is None:
            return self._smoothed_speed.get(track_id, 0.0)

        px, py, pt = prev
        dt = timestamp_s - pt
        if dt <= 1e-4:
            return self._smoothed_speed.get(track_id, 0.0)

        dist_m = math.hypot(x_m - px, y_m - py)
        inst_speed = min(30.0, dist_m / dt)
        prev_smooth = self._smoothed_speed.get(track_id, inst_speed)
        smoothed = 0.5 * prev_smooth + 0.5 * inst_speed
        self._smoothed_speed[track_id] = smoothed
        return round(smoothed, 2)

    def _class_for_id(self, class_id: int) -> VehicleClass:
        """Map COCO or synthetic class ID back to a VehicleClass literal."""
        for cls_name, cid in _SYNTHETIC_CLASS_IDS.items():
            if cid == class_id:
                return cls_name
        return _YOLO_COCO_TO_CLASS.get(class_id, "car")

    def process_frame(
        self,
        frame: np.ndarray,
        timestamp_s: float,
        frame_idx: int = 0,
        precomputed_detections: tuple[sv.Detections, list[VehicleClass]] | None = None,
    ) -> tuple[JunctionStatePacket, np.ndarray]:
        """Process one CCTV frame into a JunctionStatePacket and side-by-side visual."""
        if precomputed_detections is not None:
            detections, _classes = precomputed_detections
        else:
            detections, _classes = self._detect_with_yolo(frame)

        tracked = self.tracker.update_with_detections(detections)

        bev_vehicles: list[BEVVehicle] = []
        annotated = frame.copy()
        roi_pts = self.mapper.src_pixel_points.astype(np.int32)
        cv2.polylines(annotated, [roi_pts], isClosed=True, color=(56, 189, 248), thickness=2)

        for idx in range(len(tracked)):
            x1, y1, x2, y2 = (float(v) for v in tracked.xyxy[idx])
            track_id = (
                int(tracked.tracker_id[idx])
                if tracked.tracker_id is not None
                else None
            )
            class_id = (
                int(tracked.class_id[idx]) if tracked.class_id is not None else 2
            )
            conf = (
                float(tracked.confidence[idx])
                if tracked.confidence is not None
                else 0.9
            )
            v_class = self._class_for_id(class_id)
            x_m, y_m = self.mapper.bbox_bottom_center_to_bev((x1, y1, x2, y2))
            speed_mps = self._estimate_speed_mps(track_id, x_m, y_m, timestamp_s)

            bev_vehicles.append(
                BEVVehicle(
                    track_id=track_id,
                    vehicle_class=v_class,
                    x_m=x_m,
                    y_m=y_m,
                    speed_mps=speed_mps,
                    confidence=conf,
                )
            )

            box_color = (0, 0, 255) if v_class == "ambulance" else (34, 197, 94)
            cv2.rectangle(
                annotated,
                (int(x1), int(y1)),
                (int(x2), int(y2)),
                box_color,
                thickness=2,
            )
            label = f"#{track_id if track_id is not None else '?'} {v_class} {speed_mps:.1f}m/s"
            cv2.putText(
                annotated,
                label,
                (int(x1), max(18, int(y1) - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                box_color,
                1,
                cv2.LINE_AA,
            )

        metrics = self.mapper.compute_metrics(bev_vehicles)
        bev_map = self.mapper.render_bev_map(
            bev_vehicles,
            metrics,
            frame_idx=frame_idx,
            width_px=360,
            height_px=annotated.shape[0],
        )
        composite = np.hstack([annotated, bev_map])

        inflow_vps = round(min(3.0, len(bev_vehicles) * 0.12), 3)
        outflow_vps = round(
            min(3.0, sum(1 for v in bev_vehicles if v.speed_mps > 4.0) * 0.18),
            3,
        )

        packet = JunctionStatePacket(
            junction_id=self.junction_id,
            timestamp=round(max(0.0, timestamp_s), 3),
            source="cctv",
            active_phase=SignalPhase.NS_GREEN,
            phase_elapsed_s=round(timestamp_s % 30.0, 2),
            spatial_occupancy_ratio=metrics.spatial_occupancy_ratio,
            pcu_density=metrics.pcu_density,
            queue_length_m=metrics.queue_length_m,
            link_length_m=self.mapper.corridor_length_m,
            avg_speed_mps=metrics.avg_speed_mps,
            inflow_rate_vps=inflow_vps,
            outflow_rate_vps=outflow_vps,
            vehicle_mix=metrics.vehicle_mix,
            ev_detected=metrics.ev_detected,
            ev_confidence=metrics.ev_confidence,
            ev_eta_s=metrics.ev_eta_s,
            ev_distance_m=metrics.ev_distance_m,
        )
        return packet, composite

    def post_state_packet(self, packet: JunctionStatePacket) -> dict[str, Any] | None:
        """Stream a JunctionStatePacket to the FastAPI backend gateway."""
        if self._http_client is None or self.api_url is None:
            return None
        url = f"{self.api_url}/api/v1/junctions/{self.junction_id.value}/state"
        response = self._http_client.post(url, json=packet.model_dump(mode="json"))
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    def run_synthetic_stream(
        self,
        max_frames: int = 30,
        show: bool = False,
        emit_interval_s: float = 1.0,
    ) -> list[JunctionStatePacket]:
        """Run synthetic Indian traffic stream, emit 1Hz packets, and optionally POST."""
        packets: list[JunctionStatePacket] = []
        last_emit_t = -emit_interval_s

        for frame_idx in range(max_frames):
            t_s = frame_idx / self.fps
            frame, detections, classes = self.generate_synthetic_frame(frame_idx)
            packet, composite = self.process_frame(
                frame=frame,
                timestamp_s=t_s,
                frame_idx=frame_idx,
                precomputed_detections=(detections, classes),
            )

            if t_s - last_emit_t >= emit_interval_s - 1e-6:
                packets.append(packet)
                last_emit_t = t_s
                if self.api_url:
                    try:
                        self.post_state_packet(packet)
                    except httpx.HTTPError as exc:
                        logger.warning("Failed to stream packet to %s: %s", self.api_url, exc)

            if show:
                cv2.imshow("AegisFlow CCTV + BEV Occupancy", composite)
                if cv2.waitKey(int(1000 / self.fps)) & 0xFF == ord("q"):
                    break

        if show:
            cv2.destroyAllWindows()
        return packets

    def run_video_stream(
        self,
        video_path: str | Path,
        max_frames: int | None = None,
        show: bool = False,
        emit_interval_s: float = 1.0,
    ) -> list[JunctionStatePacket]:
        """Run YOLOv11n + ByteTrack on a video file and emit 1Hz JunctionStatePackets."""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise FileNotFoundError(f"Unable to open video source: {video_path}")

        packets: list[JunctionStatePacket] = []
        last_emit_t = -emit_interval_s
        frame_idx = 0

        try:
            while True:
                if max_frames is not None and frame_idx >= max_frames:
                    break
                ok, frame = cap.read()
                if not ok:
                    break

                t_s = frame_idx / self.fps
                packet, composite = self.process_frame(
                    frame=frame,
                    timestamp_s=t_s,
                    frame_idx=frame_idx,
                )

                if t_s - last_emit_t >= emit_interval_s - 1e-6:
                    packets.append(packet)
                    last_emit_t = t_s
                    if self.api_url:
                        try:
                            self.post_state_packet(packet)
                        except httpx.HTTPError as exc:
                            logger.warning("Failed to stream packet: %s", exc)

                if show:
                    cv2.imshow("AegisFlow CCTV + BEV Occupancy", composite)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

                frame_idx += 1
                if not show:
                    time.sleep(0.001)
        finally:
            cap.release()
            if show:
                cv2.destroyAllWindows()

        return packets


def _parse_args() -> argparse.Namespace:
    """Parse CLI flags for RoadsidePerceptionNode."""
    parser = argparse.ArgumentParser(description="AegisFlow Roadside Perception Node")
    parser.add_argument("--video", type=str, default=None, help="Path to CCTV video file.")
    parser.add_argument(
        "--demo-synthetic",
        action="store_true",
        help="Run built-in synthetic Indian traffic stream with approaching ambulance.",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=None,
        help="Gateway base URL, e.g. http://127.0.0.1:8000",
    )
    parser.add_argument("--max-frames", type=int, default=50, help="Max frames to process.")
    parser.add_argument("--show", action="store_true", help="Display OpenCV composite window.")
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint for RoadsidePerceptionNode."""
    args = _parse_args()
    node = RoadsidePerceptionNode(
        junction_id=JunctionID.J_A,
        demo_synthetic=args.demo_synthetic or args.video is None,
        api_url=args.api_url,
    )
    try:
        if args.video and not args.demo_synthetic:
            packets = node.run_video_stream(
                video_path=args.video,
                max_frames=args.max_frames,
                show=args.show,
            )
        else:
            packets = node.run_synthetic_stream(
                max_frames=args.max_frames,
                show=args.show,
            )
        print(f"Emitted {len(packets)} JunctionStatePacket(s) for {JunctionID.J_A.value}.")
    finally:
        node.close()


if __name__ == "__main__":
    main()
