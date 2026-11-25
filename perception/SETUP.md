# Perception Module - Local Environment Setup

## Verified Tool Versions

```text
=== AegisFlow Perception Environment Report ===
OS / Platform : Windows-11-10.0.26300-SP0
Python        : 3.14.0
PyTorch       : 2.15.0+cpu
Inference Mode: CPU [CPU only]
Ultralytics   : 8.4.218
OpenCV        : 5.1.0
Supervision   : 0.32.2
NumPy         : 2.5.5
SciPy         : 1.18.1
Librosa       : 1.0.1
Status        : OK
```

## Hardware Inference Note
- Check the Inference Mode line above to see whether GPU (CUDA) or CPU inference is active on this laptop.
- For local CPU-only testing, prefer nano-sized weights (such as yolo11n.pt or yolov8n.pt) to keep frame latency low.
