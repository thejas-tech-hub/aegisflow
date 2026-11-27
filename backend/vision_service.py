"""Backend bridge service wrapping RoadsidePerceptionNode for live REST snapshots."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

import cv2

from perception.detector import RoadsidePerceptionNode
from schemas.contracts import JunctionID, JunctionStatePacket

DEFAULT_RAW_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


@dataclass(frozen=True)
class VisionSnapshot:
    """Single perception snapshot with base64 composite JPEG and JunctionStatePacket."""

    frame_jpeg_b64: str
    packet: JunctionStatePacket
    ev_triggered: bool
    frame_idx: int


class VisionStreamService:
    """Manages a RoadsidePerceptionNode for on-demand CCTV + BEV snapshots."""

    def __init__(
        self,
        raw_data_dir: Path | str = DEFAULT_RAW_DATA_DIR,
        fps: float = 10.0,
    ) -> None:
        """Initialize perception node in synthetic mode or with optional .mp4 in data/raw/."""
        self.raw_data_dir = Path(raw_data_dir)
        self.fps = fps
        self.video_path: Path | None = self._discover_mp4(self.raw_data_dir)
        self.node = RoadsidePerceptionNode(
            junction_id=JunctionID.J_A,
            fps=fps,
            demo_synthetic=self.video_path is None,
        )
        self._cap: cv2.VideoCapture | None = None
        self.frame_idx: int = 0
        self.latest_packet: JunctionStatePacket | None = None
        self.latest_jpeg_b64: str | None = None

    @staticmethod
    def _discover_mp4(raw_dir: Path) -> Path | None:
        """Return the first .mp4 file in data/raw/ if present, else None."""
        if not raw_dir.is_dir():
            return None
        mp4_files = sorted(raw_dir.glob("*.mp4"))
        return mp4_files[0] if mp4_files else None

    def _read_video_frame(self) -> cv2.typing.MatLike | None:
        """Read next frame from optional .mp4, looping cleanly on EOF."""
        if self.video_path is None:
            return None
        if self._cap is None:
            self._cap = cv2.VideoCapture(str(self.video_path))
        if not self._cap.isOpened():
            return None
        ok, frame = self._cap.read()
        if not ok:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
        return frame if ok else None

    def step_snapshot(self) -> VisionSnapshot:
        """Advance perception by 1 frame and return JPEG base64 + JunctionStatePacket."""
        t_s = self.frame_idx / self.fps
        video_frame = self._read_video_frame()

        if video_frame is not None:
            packet, composite = self.node.process_frame(
                frame=video_frame,
                timestamp_s=t_s,
                frame_idx=self.frame_idx,
            )
        else:
            frame, detections, classes = self.node.generate_synthetic_frame(
                frame_idx=self.frame_idx,
            )
            packet, composite = self.node.process_frame(
                frame=frame,
                timestamp_s=t_s,
                frame_idx=self.frame_idx,
                precomputed_detections=(detections, classes),
            )

        ok, encoded = cv2.imencode(
            ".jpg",
            composite,
            [int(cv2.IMWRITE_JPEG_QUALITY), 82],
        )
        if not ok:
            raise RuntimeError("Failed to JPEG-encode perception composite frame.")

        frame_jpeg_b64 = base64.b64encode(encoded.tobytes()).decode("ascii")
        self.latest_packet = packet
        self.latest_jpeg_b64 = frame_jpeg_b64
        current_idx = self.frame_idx
        self.frame_idx += 1

        return VisionSnapshot(
            frame_jpeg_b64=frame_jpeg_b64,
            packet=packet,
            ev_triggered=packet.ev_detected,
            frame_idx=current_idx,
        )

    def get_latest_or_step_packet(self) -> JunctionStatePacket:
        """Return latest captured CCTV JunctionStatePacket, stepping once if none yet."""
        if self.latest_packet is not None:
            return self.latest_packet
        return self.step_snapshot().packet

    def close(self) -> None:
        """Release video capture and perception HTTP resources."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self.node.close()
