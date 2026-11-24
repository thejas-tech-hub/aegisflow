# AegisFlow Engineering & AI Agent Rules

## 1. Core Architectural Invariants
- **Contract-First:** All inter-module payloads MUST import Pydantic v2 models from `schemas/contracts.py`. Never invent ad-hoc JSON dictionaries between modules.
- **Safety Isolation:** The `orchestrator/` module NEVER sends signal commands directly to SUMO or signal hardware. Every proposed command MUST pass through `safety_shield/` first.
- **Decoupled Perception:** Both real CCTV (`perception/`) and SUMO (`sim/`) MUST emit the identical `JunctionStatePacket` schema.

## 2. Strict Folder Ownership (Do Not Modify Other Modules Without a Contract PR)
- `schemas/`, `predictor/`, `orchestrator/`, `safety_shield/` -> Owner: Thejas J
- `perception/` -> Owner: Veekshith R
- `sim/` -> Owner: Mohamed Dhul Kifl
- `backend/`, `frontend/` -> Owner: Mohamed Nisaruddin

## 3. Coding Standards
- **Python:** Version 3.11+, strict type hints on all functions, Pydantic v2 for data models, `pytest` for unit tests, `ruff` for linting/formatting.
- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS. No untyped `any` in telemetry handlers.
- **Git Commits:** Use Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`).
- **Testing:** Every PR adding core logic MUST include at least one unit test in `tests/`.