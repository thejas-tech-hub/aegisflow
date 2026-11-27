# sim/ Module – Environment Setup Log

> **Module Owner:** Mohamed Dhul Kifl
> **Generated:** 2026-11-27

---

## Installed Versions

| Component      | Version            |
|----------------|--------------------|
| **Python**     | 3.14.7             |
| **SUMO**       | 1.28.0 (Eclipse)   |
| **netconvert** | 1.28.0             |
| **SUMO_HOME**  | `C:\Program Files (x86)\SUMO\` |

### SUMO Build Features

```
Windows-10.0.17763 AMD64 MSVC 19.51.36256.0 Release
FMI Proj GUI FMT Intl SWIG Parquet Eigen
```

## Terminal Verification

```
> sumo --version
Eclipse SUMO sumo 1.28.0

> netconvert --version
Eclipse SUMO netconvert 1.28.0
```

## Python Packages (`sim/requirements.txt`)

| Package    | Installed Version |
|------------|-------------------|
| traci      | 1.28.0            |
| sumolib    | 1.28.0            |
| libsumo    | 1.28.0            |
| sumo-data  | 1.28.0            |
| numpy      | 2.5.5             |
| pandas     | 3.1.1             |
| matplotlib | 3.11.2            |

All packages installed into the project virtual environment at `.venv/`.

## Network Build Verification

```
> python sim/network/build_network.py
Using netconvert: C:\Program Files (x86)\SUMO\bin\netconvert.EXE
SUCCESS: corridor.net.xml generated (33.8 KB)
```

`sim/network/corridor.net.xml` compiled with **zero errors** from:
- `corridor.nod.xml` — 3 signalised junctions + 8 boundary nodes
- `corridor.edg.xml` — 24 bidirectional edges (arterial + cross-streets)
- `corridor.tll.xml` — 6-phase signal programs for J_A, J_B, J_C

## Notes

- SUMO was installed via `winget install EclipseFoundation.SUMO --version 1.28.0`.
- System `PATH` includes `C:\Program Files (x86)\SUMO\bin` and `...\tools`.
- If `sumo` / `netconvert` are not found in a new terminal, ensure `SUMO_HOME` is set
  and `%SUMO_HOME%\bin` is on `PATH`.
