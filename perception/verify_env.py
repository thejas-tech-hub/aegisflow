import platform
import sys

import cv2
import librosa
import numpy as np
import scipy
import supervision as sv
import torch
import ultralytics


def main() -> None:
    cuda_available: bool = torch.cuda.is_available()
    device_name: str = torch.cuda.get_device_name(0) if cuda_available else "CPU only"

    print("=== AegisFlow Perception Environment Report ===")
    print(f"OS / Platform : {platform.platform()}")
    print(f"Python        : {sys.version.split()[0]}")
    print(f"PyTorch       : {torch.__version__}")
    print(f"Inference Mode: {'GPU (CUDA)' if cuda_available else 'CPU'} [{device_name}]")
    print(f"Ultralytics   : {ultralytics.__version__}")
    print(f"OpenCV        : {cv2.__version__}")
    print(f"Supervision   : {sv.__version__}")
    print(f"NumPy         : {np.__version__}")
    print(f"SciPy         : {scipy.__version__}")
    print(f"Librosa       : {librosa.__version__}")
    print("Status        : OK")


if __name__ == "__main__":
    main()
