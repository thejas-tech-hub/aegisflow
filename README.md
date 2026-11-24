# AegisFlow
**Predictive Emergency Corridor Orchestration with Inter-Junction Traffic Intelligence**

AegisFlow shifts emergency vehicle priority from isolated, reactive signal preemption to predictive multi-junction corridor coordination with deterministic municipal safety verification.

## Module Map
- `schemas/` — Shared Pydantic v2 data contracts
- `perception/` — YOLOv11 + ByteTrack heterogeneous detection, Homography BEV spatial occupancy & multi-modal EV fusion
- `sim/` — Eclipse SUMO 3-junction heterogeneous corridor digital twin & A/B benchmarking
- `predictor/` — Physics-informed (CTM) + LightGBM 30–60s queue & spillback forecaster
- `orchestrator/` — Spillback-aware rolling-horizon multi-junction signal controller
- `safety_shield/` — Deterministic municipal signal invariant verifier (Mutex, Min-Green, Clearance, Anti-Starvation)
- `backend/` — FastAPI inter-junction API gateway, event bus & WebSocket broadcaster
- `frontend/` — React + TypeScript real-time corridor command center

## Team
- **Thejas J** — Architecture, Predictor, Orchestrator & Safety Shield
- **Veekshith R** — Computer Vision, Spatial Occupancy & EV Fusion
- **Mohamed Dhul Kifl** — SUMO Digital Twin, TraCI Bridge & Benchmarks
- **Mohamed Nisaruddin** — Backend API Infrastructure & Command Center UI