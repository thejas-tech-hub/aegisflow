# AegisFlow v2.0 — 8-Minute Live Demo & Examiner Viva Playbook

This field guide provides an exact, timed **8-minute live demo choreography** paired with a **Top 10 Examiner Viva Q&A Defense Guide** anchored strictly to the implemented architecture, telemetry contracts, and benchmark evidence.

---

## Part 1: 8-Minute Live Demo Choreography

> **Pre-Flight (Before Examiners Enter):**
> Run `.\start_demo.ps1` from repo root. Verify `WS Connected` (emerald pill) on `http://localhost:5173`, preset set to **Peak Spillback**, viewport in **3D Digital Twin**, and optional edge terminal ready:
> `python -m perception.detector --demo-synthetic --show --api-url http://127.0.0.1:8000`

---

### Minute 0–2: The Spillback Problem & Baseline Trap
- **UI State:** `Dashboard` tab, preset `Peak Spillback`, camera preset `Overview`.
- **Actions:**
  1. Point to the 3 junctions along the `900 m` eastbound corridor: **`J_A` (`0 m`, Upstream Entry)**, **`J_B` (`300 m`, Spillback Chokepoint)**, and **`J_C` (`600 m`, Downstream Exit)**.
  2. Click **Dispatch EV** and **Play** (keep speed at `1x` or `2x`).
  3. Focus briefly on the **red Track A lane (Baseline EVP)** and the **Junction `J_B` Queue Trajectory** dashed rose curve climbing past the `234 m` (`78%`) red limit line (`190 m` initial standing queue swelling to `278.0 m`).
- **Talking Points:**
  - Conventional EVP (`IsolatedEVPController`) is **spatially myopic**: it knows nothing upstream or downstream until an ambulance enters `<= 110 m` of a junction.
  - Because `J_A` flushes blindly onto green without checking `J_B`, it pours upstream traffic straight into an already congested `J_B`. Within seconds, Track A shows **`TRAPPED IN SPILLBACK`** (`45.8 s` halted, `112.8 s` total travel time).

---

### Minute 2–4: Live CCTV + BEV Spatial Occupancy Vision Tab
- **Actions:**
  1. Launch (or bring forward) the live OpenCV perception node:
     ```powershell
     python -m perception.detector --demo-synthetic --show --api-url http://127.0.0.1:8000
     ```
     Show the oblique CCTV detection boxes (motorcycles, auto-rickshaws, cars, buses, approaching ambulance with strobe) alongside the **top-down `7 m x 50 m` BEV Spatial Occupancy mini-map**.
  2. Switch the browser left rail to the **Corridor** tab (`CorridorDetailView`) to show:
     - Per-junction `+45s` Predictive Horizon cards (`Now` solid occupancy bar vs. translucent `+45s Forecast` ghost bar against the `78%` spillback line).
     - Live Indian heterogeneous mix pills (`Bikes`, `Autos`, `Cars`, `Buses`, and weighted `PCU` density) alongside the **2D Schematic BEV Race Canvas**.
- **Talking Points:**
  - Emphasize the **Decoupled Perception Contract**: both the YOLOv11n+ByteTrack CCTV pipeline (`perception/`) and SUMO (`sim/`) emit the exact same `~1.2 KB` `JunctionStatePacket` Pydantic v2 schema over `POST /api/v1/junctions/{junction_id}/state`.
  - Highlight why we measure **ground-plane area coverage (`spatial_occupancy_ratio`) + Indian PCU density** instead of naive western vehicle counts.

---

### Minute 4–6: Live 3D Dual-Track Race, API Arcs & Safety Shield
- **Actions:**
  1. Return to the **Dashboard** tab. Click **Reset** $\to$ **Dispatch EV** $\to$ **Play** if the first episode already finished, or switch camera presets (`Aegis EV`, `J_B`, `Baseline`) and toggle briefly to **2D Schematic** and back to **3D Digital Twin** to showcase crisp 60 FPS WebGL telemetry + `UnrealBloomPass`.
  2. Point directly to three live synchronization signals on screen:
     - **Glowing Cyan/Amber Inter-Junction API Arcs** above the 3D roadway (`J_A -> J_B` `EV_SPILLBACK_ALERT`, `J_B -> J_A` `SPILLBACK_METERING_BACKPRESSURE`, `J_B -> J_C` `EV_GREEN_WAVE_HANDOFF`).
     - **Live Tactical Narration** pills updating in plain English (`RED_TRUNCATION` **Early Flush** at `J_B` + `UPSTREAM_METERING` throttling inflow at `J_A` before the ambulance reaches `J_B`).
     - **Deterministic Safety Shield Interlock** (bottom-right dock): point out live `APPROVED`, `CLIPPED`, and `VETOED` log rows showing `MANDATORY_CLEARANCE`, `MIN_GREEN_LOCK`, and the **Zero (`0 — Verified`) Unsafe Transitions** counter.
- **Talking Points:**
  - AegisFlow clears `J_B` *before* the ambulance arrives (`4.0 s` stopped vs. `45.8 s` stopped in `peak_spillback`, `71.0 s` vs. `112.8 s` total travel time), while never bypassing a single `3 s` yellow or `2 s` all-red interval.

---

### Minute 6–8: 30-Seed Statistical Proof & Fault-Injection Resilience
- **Actions:**
  1. Click **Run Full A/B Benchmark** in the top command bar (or open the **Analytics** tab) to run a live deterministic episode report and show the embedded **30-Seed Monte Carlo & Fault-Injection Summary Table**.
  2. Reference the three dark-mode benchmark figures in `docs/benchmarks/` (`ev_travel_time_comparison.png`, `spillback_and_halting_reduction.png`, `fault_injection_robustness.png`) or [EVALUATION_SUMMARY.md](benchmarks/EVALUATION_SUMMARY.md).
- **Talking Points:**
  - In **`severe_gridlock`**, Fixed-Time (`300.0 s`) and Isolated Local EVP (`300.0 s`, `95.3` spillback ticks) completely stall and fail to clear the `300 s` horizon; AegisFlow clears cleanly in **`86.0 s`** with **`0.0` spillback ticks** and **`0` safety violations**.
  - Under adversarial faults (`+/-15%` sensor noise and `30%` API packet loss), performance degrades by only **`+0.10 s`** (`71.00 s` $\to$ `71.10 s`) with zero spillback and zero safety violations.

---

## Part 2: Top 10 Examiner Viva Q&A Defense Guide

### Q1. Why use BEV Spatial Occupancy & Indian PCU Weighting instead of standard Vehicle Counting?
**Answer:**
In heterogeneous, non-lane-disciplined Indian traffic, raw vehicle counts fail completely as a congestion proxy: 10 weaving motorcycles cover roughly `16.0 m²` (`0.5` PCU each = `5.0` PCU), whereas 2 buses or trucks cover `48–55 m²` (`3.0` PCU each = `6.0` PCU) and physically block turning pockets.
In `perception/spatial.py` (`BEVSpatialMapper`), we warp oblique bounding-box bottom centers onto a calibrated `7 m x 50 m` (`350 m²`) metric ground plane using 4-point OpenCV homography (`cv2.getPerspectiveTransform`), then sum physical class footprints (`1.6 m²` motorcycle, `3.6 m²` auto-rickshaw, `8.5 m²` car, `27.5 m²` bus, `24.0 m²` truck, `10.5 m²` ambulance from `perception/calibration_config.json`) to compute `spatial_occupancy_ratio` (`0.0–1.0`) alongside PCU-weighted density (`6.5 m` effective longitudinal spacing per PCU in `PredictorConfig`). That gives an invariant physical fill metric across any traffic composition.

---

### Q2. Why use a Physics-Informed CTM + Online Residual Calibration instead of pure Deep RL or a black-box LSTM?
**Answer:**
1. **Zero-Shot Physical Generalization & Interpretability:** Pure Deep RL or sequence LSTMs require tens of thousands of regime-matched episodes, struggle when link lengths or signal geometry shift, and cannot explain *why* they flushed a downstream junction (`Reason: Proactive Queue Flush: EV ETA 28.0s at J_B & spillback risk 0.89`). `SpillbackPredictor` (`predictor/forecaster.py`) embeds conservation of flow via Cell Transmission platoon propagation (`upstream outflow` attenuated by dynamic free-link travel delay $\tau = L_{\text{free}} / v_{\text{eff}}$), phase-aware saturation discharge (`0.65 veh/s` base across `2` effective lanes), and queue shockwave delay ahead of the EV.
2. **Online Sim-to-Real Adaptation:** Systematic model mismatch (e.g., local double-parking or bus stop dwell bias) is corrected online by `ResidualCalibrationHook` via an exponentially weighted residual update ($\alpha = 0.25$) with ridge shrinkage ($\lambda = 0.05$) clamped to $\pm 45\text{ m}$ — without needing GPU retraining on the pole.
3. **Guaranteed Predictability:** Every forecast falls inside physically bounded `[0, 1.5 * link_length]` constraints before feeding the Simplex Safety Shield.

---

### Q3. How does the Deterministic Safety Shield (Simplex Architecture) guarantee 0% unsafe transitions?
**Answer:**
We strictly decouple intelligence from actuation (**Safety Isolation** invariant in `.antigravity/rules.md`). `CorridorOrchestrator` only emits *advisory* `ProposedControlAction` objects. Before any command reaches `sim/`, hardware, or telemetry logs, `DeterministicSafetyShield.verify()` (`safety_shield/shield.py`) evaluates **5 non-negotiable municipal invariants in strict priority order**:
1. **`MANDATORY_CLEARANCE`**: Locks active yellow (`3.0 s`) and all-red (`2.0 s`) intervals; vetoes early preemption or skipping clearance.
2. **`MAX_RED_STARVATION`**: Overrides green holds/extensions once opposing cross-street wait exceeds `110.0 s`.
3. **`CONFLICT_MUTEX`**: Rejects illegal non-adjacent direct green-to-green transitions (`EW_GREEN <-> NS_GREEN`), routing safely through the 6-state ring (`GREEN -> YELLOW -> ALL_RED -> OPPOSING_GREEN`).
4. **`MIN_GREEN_LOCK`**: Enforces a `10.0 s` minimum green floor against `RED_TRUNCATION`.
5. **`DURATION_BOUNDS`**: Clamps requested green durations to `[10.0 s, 75.0 s]`.

Every verdict (`APPROVED`, `CLIPPED`, or `VETOED` with `violated_invariants`) is logged deterministically and persisted to SQLite (`backend/telemetry.db`). Even if the orchestrator or an adversarial test injects malformed/unsafe actions, unsafe actuation is structurally impossible (`0` safety violations across all `30` Monte Carlo + stress runs).

---

### Q4. How does AegisFlow behave under ±15% CCTV estimation noise or 30% inter-junction API packet loss?
**Answer:**
Verified quantitatively in our fault-injection stress suite (`orchestrator/evaluation_suite.py`, `10` seeds on `peak_spillback`):
- **Under `+/-15%` Perception Noise:** EV travel time stays **`71.00 ± 0.00 s`**, stopped time stays **`4.00 ± 0.00 s`**, spillback ticks **`0.0`**, safety violations **`0`**. Why? `SpillbackPredictor._compute_trends()` smooths instantaneous inflow (`0.6 * current + 0.4 * trailing_10_tick_mean`), computes queue velocity `dQ/dt` across a rolling `history_window`, and couples upstream platoon mass rather than over-reacting to single-frame detector jitter.
- **Under `30%` Upstream Packet Drop:** EV travel time rises by only **`+0.10 s`** (`71.10 ± 0.30 s`), stopped time **`4.10 ± 0.30 s`**, peak queue **`198.3 ± 0.5 m`**, with **`0.0` spillback ticks** and **`0` safety violations** (vs. clean Baseline EVP at `112.70 s` and `18.0` spillback ticks). Why? Because upstream alerts repeat at `1 Hz` across the `10–55 s` flush window (`OrchestratorConfig`), any dropped packet is superseded within `1–2 s`, and downstream junctions retain stale last-known-good state/local detection fallback without stalling signal progression.

---

### Q5. Why stream compact JSON telemetry (~1.2 KB/s) instead of centralizing raw CCTV video feeds?
**Answer:**
1. **400×–800× Bandwidth Reduction:** A single 1080p RTSP/H.264 roadside stream requires ~`4–8 Mbps` (`500–1,000 KB/s`). A 30-junction city corridor would saturate `120–240 Mbps` backhaul just to move pixels. By running `YOLOv11n + ByteTrack + BEV` inference on edge compute at the junction cabinet and emitting `JunctionStatePacket` (`schemas/contracts.py`) at `1 Hz`, each junction consumes only **~1.2 KB/s** (`< 40 KB/s` for 30 junctions), easily carried over existing LTE/4G or municipal fiber/LoRaWAN backhaul.
2. **Low Latency & Deterministic Contract:** FastAPI validates and ingests a `1.2 KB` Pydantic v2 packet in sub-millisecond time.
3. **Privacy by Design:** Zero raw video frames, faces, or license plates ever leave the intersection perimeter.

---

### Q6. How does AegisFlow scale from 3 junctions (`J_A`, `J_B`, `J_C`) to a 30-junction city corridor?
**Answer:**
- **Linear $O(N)$ Message Passing:** Neither `SpillbackPredictor` nor `CorridorOrchestrator` forms a global $O(N^2)$ joint MDP state space. Topology is configured declaratively via `PredictorConfig.corridor_topology` (directed upstream-to-downstream adjacency) and `OrchestratorConfig.corridor_order`. Each junction evaluates only its own local packet, its immediate upstream feeder outflow, and its immediate downstream spillback risk (`N` local steps per `1 s` tick).
- **Sub-Millisecond Compute Budget:** At `1 Hz` control frequency, a pure-Python/NumPy forward CTM + FSM shield pass takes fractions of a millisecond per junction (`~3–10 ms` total for 30 junctions), well inside the `1,000 ms` tick budget, and independent arterial corridors shard horizontally behind the async FastAPI gateway.

---

### Q7. How do you ensure the A/B comparison against Isolated Local EVP is scientifically fair?
**Answer:**
Both controllers share identical physics, random seeds, demand inflows, and municipal safety rules inside `DualTrackABRunner` (`orchestrator/ab_runner.py`):
- `baseline_sim` and `aegisflow_sim` are instantiated as two matched `CorridorPhysicsSim(scenario=scenario, seed=seed)` instances experiencing identical vehicle arrivals and initial queues.
- Critically, `IsolatedEVPController` (`orchestrator/baseline_evp.py`) also routes all its proposed actions through its own `DeterministicSafetyShield` instance so Track A cannot "cheat" via unsafe instant green jumps, isolating solely the causal value of **inter-junction lookahead + upstream metering** over localized `110 m` preemption.

---

### Q8. Once the emergency vehicle passes, how do cross-streets recover without long-term starvation?
**Answer:**
Cross-street recovery operates on two complementary layers:
1. **Opportunistic AI Recovery (`orchestrator/controller.py`):** `_update_ev_clearance_state()` sets `ev_recently_cleared[junction_id] = True` the moment an EV clears the junction approach, adding `max_pressure_switch_threshold + 10.0` pressure bias toward returning to `NS_GREEN` (`ControlActionType.RECOVERY`). During normal flow, Max-Pressure scoring continuously balances accumulated cross-street wait against arterial queue pressure.
2. **Hard Deterministic Ceiling (`safety_shield/shield.py`):** Invariant 2 (`MAX_RED_STARVATION`) guarantees that if `opposing_red_wait_s > 110.0 s`, `DeterministicSafetyShield` forcefully vetoes any `HOLD` or `GREEN_EXTENSION` and triggers yellow clearance toward the cross-street.

---

### Q9. How do you prevent Sim-to-Real drift between the SUMO Digital Twin and real roadside CCTV cameras?
**Answer:**
Architectural **Sim-to-Real Contract Parity** (`schemas/contracts.py`): both `perception/` (`source="cctv"`) and `sim/` (`source="sumo"`) serialize into the single strict `JunctionStatePacket` contract (`ConfigDict(extra="forbid")`). Because `predictor/`, `orchestrator/`, `safety_shield/`, and `backend/` consume *only* `JunctionStatePacket`, the downstream control stack has zero camera-specific or simulator-specific branches. Meanwhile, field geometry differences (road width/length, class footprints, PCU weights) live purely in `perception/calibration_config.json`, and dynamic discharge mismatches are absorbed online by `ResidualCalibrationHook`.

---

### Q10. What happens if tall vehicles (buses/trucks) partially occlude smaller two-wheelers in oblique CCTV angles?
**Answer:**
1. **Ground-Plane Bottom-Center Projection:** `BEVSpatialMapper.bbox_bottom_center_to_bev()` projects `( (x1+x2)/2, y2 )` — the tire-to-asphalt contact point — rather than bounding-box centers, eliminating height-induced perspective parallax error along the `50 m` BEV corridor.
2. **Temporal Tracking Persistence:** ByteTrack (with IoU/centroid fallback in `perception/detector.py`) preserves persistent `tracker_id` speeds and trajectories across brief inter-frame occlusions.
3. **Shockwave-Safe Conservatism:** Even if `<= 15%` transient undercounting occurs in dense platoons, our stress benchmark verifies `0.00 s` EV delay drift (`71.00 s` at `+/-15%` noise) because queue length (`queue_length_m`) tracks the physical tail of slowed vehicles (`speed_mps <= 4.0`) and `ResidualCalibrationHook` automatically adjusts persistent bias.
