"""Homography Bird's-Eye View (BEV) spatial occupancy mapper and mini-map renderer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from schemas.contracts import VehicleMix

VehicleClass = Literal[
    "motorcycle",
    "auto_rickshaw",
    "car",
    "bus",
    "truck",
    "ambulance",
]

DEFAULT_CALIBRATION_PATH = Path(__file__).resolve().parent / "calibration_config.json"

_DEFAULT_DIMENSIONS_M: dict[VehicleClass, tuple[float, float]] = {
    "motorcycle": (0.8, 2.0),
    "auto_rickshaw": (1.4, 2.6),
    "car": (1.8, 4.5),
    "bus": (2.5, 11.0),
    "truck": (2.5, 9.6),
    "ambulance": (2.0, 5.2),
}

_CLASS_COLORS_BGR: dict[VehicleClass, tuple[int, int, int]] = {
    "motorcycle": (245, 200, 30),
    "auto_rickshaw": (30, 190, 255),
    "car": (235, 155, 70),
    "bus": (210, 105, 175),
    "truck": (180, 95, 145),
    "ambulance": (50, 50, 255),
}


@dataclass(frozen=True)
class VehicleClassSpec:
    """Physical footprint area and Indian PCU weight for a vehicle class."""

    footprint_area_m2: float
    pcu_weight: float


@dataclass(frozen=True)
class BEVVehicle:
    """Tracked vehicle projected into metric Bird's-Eye View coordinates."""

    track_id: int | None
    vehicle_class: VehicleClass
    x_m: float
    y_m: float
    speed_mps: float = 0.0
    confidence: float = 0.9


@dataclass(frozen=True)
class BEVMetrics:
    """Aggregated corridor spatial occupancy, PCU density, queue, and EV metrics."""

    spatial_occupancy_ratio: float
    pcu_density: float
    queue_length_m: float
    avg_speed_mps: float
    vehicle_mix: VehicleMix
    ev_detected: bool
    ev_confidence: float
    ev_eta_s: float | None
    ev_distance_m: float | None


class BEVSpatialMapper:
    """Projects oblique CCTV pixels into metric BEV coordinates and renders a 2D mini-map."""

    def __init__(
        self,
        calibration_path: Path | str = DEFAULT_CALIBRATION_PATH,
    ) -> None:
        """Load 4-point homography and Indian vehicle class specs from JSON config."""
        self.calibration_path = Path(calibration_path)
        with self.calibration_path.open("r", encoding="utf-8-sig") as f:
            config = json.load(f)

        homography_cfg = config["homography"]
        dims = homography_cfg["corridor_dimensions_meters"]
        self.corridor_width_m: float = float(dims["width"])
        self.corridor_length_m: float = float(dims["length"])
        self.road_area_m2: float = self.corridor_width_m * self.corridor_length_m

        self.src_pixel_points = np.array(
            homography_cfg["src_pixel_points"],
            dtype=np.float32,
        )
        self.dst_meter_points = np.array(
            homography_cfg["dst_meter_points"],
            dtype=np.float32,
        )
        self.homography_matrix: np.ndarray = cv2.getPerspectiveTransform(
            self.src_pixel_points,
            self.dst_meter_points,
        )

        self.vehicle_specs: dict[str, VehicleClassSpec] = {
            cls_name: VehicleClassSpec(
                footprint_area_m2=float(spec["footprint_area_m2"]),
                pcu_weight=float(spec["pcu_weight"]),
            )
            for cls_name, spec in config["vehicle_classes"].items()
        }

    def pixel_to_bev(self, u: float, v: float) -> tuple[float, float]:
        """Project pixel coordinate (u, v) to metric BEV (X, Y) in meters."""
        pts = np.array([[[u, v]]], dtype=np.float32)
        warped = cv2.perspectiveTransform(pts, self.homography_matrix)
        x_m = float(warped[0, 0, 0])
        y_m = float(warped[0, 0, 1])
        return x_m, y_m

    def bbox_bottom_center_to_bev(
        self,
        bbox_xyxy: tuple[float, float, float, float],
    ) -> tuple[float, float]:
        """Project the bottom-center of a bounding box (x1, y1, x2, y2) to BEV meters."""
        x1, _y1, x2, y2 = bbox_xyxy
        u = (x1 + x2) / 2.0
        v = y2
        return self.pixel_to_bev(u, v)

    def _in_corridor(self, vehicle: BEVVehicle) -> bool:
        """Return True if vehicle BEV coordinates lie inside the monitored road strip."""
        return (
            -1.0 <= vehicle.x_m <= self.corridor_width_m + 1.0
            and 0.0 <= vehicle.y_m <= self.corridor_length_m + 5.0
        )

    def compute_metrics(self, vehicles: list[BEVVehicle]) -> BEVMetrics:
        """Compute spatial_occupancy_ratio, pcu_density, queue_length_m, and EV telemetry."""
        corridor_vehicles = [v for v in vehicles if self._in_corridor(v)]

        total_area = 0.0
        total_pcu = 0.0
        motorcycles = 0
        auto_rickshaws = 0
        cars = 0
        buses_trucks = 0
        emergency_vehicles = 0

        ambulances: list[BEVVehicle] = []
        queued_y: list[float] = []
        speeds: list[float] = []

        for v in corridor_vehicles:
            spec = self.vehicle_specs.get(
                v.vehicle_class,
                VehicleClassSpec(footprint_area_m2=8.5, pcu_weight=1.0),
            )
            total_area += spec.footprint_area_m2
            total_pcu += spec.pcu_weight
            speeds.append(max(0.0, v.speed_mps))

            if v.speed_mps <= 4.0 and 0.0 <= v.y_m <= self.corridor_length_m:
                queued_y.append(v.y_m)

            if v.vehicle_class == "motorcycle":
                motorcycles += 1
            elif v.vehicle_class == "auto_rickshaw":
                auto_rickshaws += 1
            elif v.vehicle_class == "car":
                cars += 1
            elif v.vehicle_class in ("bus", "truck"):
                buses_trucks += 1
            elif v.vehicle_class == "ambulance":
                emergency_vehicles += 1
                ambulances.append(v)

        sor = min(1.0, max(0.0, total_area / self.road_area_m2))
        pcu_density = round((total_pcu / self.corridor_length_m) * 100.0, 3)
        queue_length_m = (
            round(min(self.corridor_length_m, max(queued_y)), 2) if queued_y else 0.0
        )
        avg_speed_mps = round(sum(speeds) / len(speeds), 2) if speeds else 0.0

        ev_detected = len(ambulances) > 0
        ev_confidence = 0.0
        ev_eta_s: float | None = None
        ev_distance_m: float | None = None
        if ambulances:
            closest = min(ambulances, key=lambda a: max(0.0, a.y_m))
            ev_distance_m = round(max(0.0, closest.y_m), 2)
            effective_speed = max(4.0, closest.speed_mps)
            ev_eta_s = round(ev_distance_m / effective_speed, 2)
            ev_confidence = round(min(1.0, max(0.0, closest.confidence)), 3)

        return BEVMetrics(
            spatial_occupancy_ratio=round(sor, 4),
            pcu_density=pcu_density,
            queue_length_m=queue_length_m,
            avg_speed_mps=avg_speed_mps,
            vehicle_mix=VehicleMix(
                motorcycles=motorcycles,
                auto_rickshaws=auto_rickshaws,
                cars=cars,
                buses_trucks=buses_trucks,
                emergency_vehicles=emergency_vehicles,
            ),
            ev_detected=ev_detected,
            ev_confidence=ev_confidence,
            ev_eta_s=ev_eta_s,
            ev_distance_m=ev_distance_m,
        )

    def render_bev_map(
        self,
        vehicles: list[BEVVehicle],
        metrics: BEVMetrics,
        frame_idx: int = 0,
        width_px: int = 360,
        height_px: int = 720,
    ) -> np.ndarray:
        """Render a dark-mode 2D Top-Down BEV Spatial Occupancy Mini-Map."""
        canvas = np.full((height_px, width_px, 3), (22, 17, 13), dtype=np.uint8)

        hud_h = 84
        pad_x = 46
        pad_bottom = 28
        road_w_px = width_px - 2 * pad_x
        road_h_px = height_px - hud_h - pad_bottom

        def meter_to_px(x_m: float, y_m: float) -> tuple[int, int]:
            px_x = int(pad_x + (x_m / self.corridor_width_m) * road_w_px)
            # Y=0 is stop line at bottom; Y=corridor_length_m is upstream at top.
            px_y = int(hud_h + (1.0 - (y_m / self.corridor_length_m)) * road_h_px)
            return px_x, px_y

        # Road asphalt surface
        cv2.rectangle(
            canvas,
            (pad_x, hud_h),
            (pad_x + road_w_px, hud_h + road_h_px),
            (38, 32, 28),
            thickness=-1,
        )
        # Road borders
        cv2.rectangle(
            canvas,
            (pad_x, hud_h),
            (pad_x + road_w_px, hud_h + road_h_px),
            (100, 115, 135),
            thickness=2,
        )

        # Dashed center lane divider and 10m grid lines
        center_x = pad_x + road_w_px // 2
        for y_step in range(hud_h + 10, hud_h + road_h_px, 24):
            cv2.line(
                canvas,
                (center_x, y_step),
                (center_x, min(y_step + 12, hud_h + road_h_px)),
                (90, 100, 115),
                thickness=1,
            )

        for dist_m in (10, 20, 30, 40, 50):
            _, gy = meter_to_px(0.0, float(dist_m))
            cv2.line(canvas, (pad_x, gy), (pad_x + road_w_px, gy), (55, 62, 72), 1)
            cv2.putText(
                canvas,
                f"{dist_m}m",
                (6, gy + 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                (148, 163, 184),
                1,
                cv2.LINE_AA,
            )

        # Stop line at Y = 0
        _, stop_y = meter_to_px(0.0, 0.0)
        cv2.line(canvas, (pad_x, stop_y), (pad_x + road_w_px, stop_y), (0, 210, 255), 3)

        # Draw scaled vehicle rectangles
        px_per_m_x = road_w_px / self.corridor_width_m
        px_per_m_y = road_h_px / self.corridor_length_m

        for v in vehicles:
            if not self._in_corridor(v):
                continue
            vw_m, vl_m = _DEFAULT_DIMENSIONS_M.get(v.vehicle_class, (1.8, 4.5))
            cx, cy = meter_to_px(v.x_m, v.y_m)
            half_w = max(4, int((vw_m * px_per_m_x) / 2.0))
            half_l = max(6, int((vl_m * px_per_m_y) / 2.0))
            x1, y1 = cx - half_w, cy - half_l
            x2, y2 = cx + half_w, cy + half_l

            color = _CLASS_COLORS_BGR.get(v.vehicle_class, (200, 200, 200))
            if v.vehicle_class == "ambulance":
                flash_on = (frame_idx // 3) % 2 == 0
                fill_color = (45, 45, 255) if flash_on else (180, 180, 255)
                border_color = (255, 255, 255) if flash_on else (0, 0, 255)
                cv2.rectangle(canvas, (x1, y1), (x2, y2), fill_color, thickness=-1)
                cv2.rectangle(
                    canvas,
                    (x1 - 2, y1 - 2),
                    (x2 + 2, y2 + 2),
                    border_color,
                    thickness=2,
                )
            else:
                cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness=-1)
                cv2.rectangle(canvas, (x1, y1), (x2, y2), (15, 23, 42), thickness=1)

        # Live HUD header
        cv2.rectangle(canvas, (0, 0), (width_px, hud_h - 4), (30, 23, 18), thickness=-1)
        cv2.putText(
            canvas,
            "BEV SPATIAL OCCUPANCY",
            (12, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (248, 250, 252),
            1,
            cv2.LINE_AA,
        )
        sor_pct = metrics.spatial_occupancy_ratio * 100.0
        cv2.putText(
            canvas,
            f"SOR: {sor_pct:5.1f}%   PCU: {metrics.pcu_density:5.1f}",
            (12, 46),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (56, 189, 248),
            1,
            cv2.LINE_AA,
        )
        ev_label = "EV ALERT" if metrics.ev_detected else f"Q: {metrics.queue_length_m:.1f}m"
        ev_color = (60, 60, 255) if metrics.ev_detected else (148, 163, 184)
        cv2.putText(
            canvas,
            ev_label,
            (12, 68),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            ev_color,
            1,
            cv2.LINE_AA,
        )
        return canvas
