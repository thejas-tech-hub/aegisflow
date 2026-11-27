# AegisFlow Monte Carlo Evaluation & Robustness Summary

- **Monte Carlo Seeds per Scenario:** `30` (seeds `1..30`)
- **Fault-Injection Seeds (`peak_spillback`):** `10` (seeds `1..10`)

## 1. Multi-Scenario Performance Comparison (Mean ± 1σ)

| Scenario | Controller | EV Travel Time (s) | EV Stopped Time (s) | Peak J_B Queue (m) | Spillback Ticks | Safety Violations |
|---|---|---:|---:|---:|---:|---:|
| `moderate_mixed` | Fixed-Time | 184.60 ± 0.55 | 117.60 ± 0.55 | 121.9 ± 0.5 | 0.0 ± 0.0 | 0 |
| `moderate_mixed` | Isolated Local EVP | 85.00 ± 0.00 | 18.00 ± 0.00 | 159.3 ± 0.5 | 0.0 ± 0.0 | 0 |
| `moderate_mixed` | AegisFlow v2.0 | 67.00 ± 0.00 | 0.00 ± 0.00 | 100.8 ± 0.2 | 0.0 ± 0.0 | 0 |
| `peak_spillback` | Fixed-Time | 259.93 ± 0.51 | 192.93 ± 0.51 | 230.8 ± 0.5 | 0.0 ± 0.0 | 0 |
| `peak_spillback` | Isolated Local EVP | 112.80 ± 0.40 | 45.80 ± 0.40 | 278.0 ± 0.5 | 18.0 ± 0.0 | 0 |
| `peak_spillback` | AegisFlow v2.0 | 71.00 ± 0.00 | 4.00 ± 0.00 | 198.1 ± 0.2 | 0.0 ± 0.0 | 0 |
| `severe_gridlock` | Fixed-Time | 300.00 ± 0.00 | 272.00 ± 0.00 | 267.7 ± 0.9 | 68.3 ± 2.4 | 0 |
| `severe_gridlock` | Isolated Local EVP | 300.00 ± 0.00 | 252.43 ± 3.05 | 300.0 ± 0.0 | 95.3 ± 4.4 | 0 |
| `severe_gridlock` | AegisFlow v2.0 | 86.00 ± 0.00 | 19.00 ± 0.00 | 228.2 ± 0.2 | 0.0 ± 0.0 | 0 |

## 2. Adversarial Fault-Injection Stress Test (`peak_spillback`)

| Mode | EV Travel Time (s) | EV Stopped Time (s) | Peak J_B Queue (m) | Spillback Ticks | Safety Violations |
|---|---:|---:|---:|---:|---:|
| AegisFlow (Clean) | 71.00 ± 0.00 | 4.00 ± 0.00 | 198.1 ± 0.2 | 0.0 ± 0.0 | 0 |
| AegisFlow (+/-15% Noise) | 71.00 ± 0.00 | 4.00 ± 0.00 | 198.1 ± 0.2 | 0.0 ± 0.0 | 0 |
| AegisFlow (30% Packet Drop) | 71.10 ± 0.30 | 4.10 ± 0.30 | 198.3 ± 0.5 | 0.0 ± 0.0 | 0 |
| Baseline EVP (Clean) | 112.70 ± 0.46 | 45.70 ± 0.46 | 277.9 ± 0.7 | 18.0 ± 0.0 | 0 |
