#!/usr/bin/env python3
"""
build_network.py – Compile the AegisFlow corridor network with netconvert.

Invokes SUMO's ``netconvert`` to merge:
    corridor.nod.xml  (nodes)
    corridor.edg.xml  (edges)
    corridor.tll.xml  (traffic-light programs)
into a single ``corridor.net.xml`` network file.

Usage:
    python sim/network/build_network.py

The script automatically resolves netconvert from:
  1. The PATH / SUMO_HOME environment variable, or
  2. The pip-installed ``sumo-data`` / ``libsumo`` package location.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_netconvert() -> str:
    """Return the path to the netconvert executable."""
    # 1. Try PATH directly
    nc = shutil.which("netconvert")
    if nc:
        return nc

    # 2. Try SUMO_HOME
    sumo_home = os.environ.get("SUMO_HOME", "")
    if sumo_home:
        candidate = Path(sumo_home) / "bin" / "netconvert"
        if candidate.exists() or candidate.with_suffix(".exe").exists():
            return str(candidate.with_suffix(".exe") if os.name == "nt" else candidate)

    # 2b. Try well-known Windows install locations
    if os.name == "nt":
        for base in [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
            Path(r"C:\Program Files"),
            Path(r"C:\Program Files (x86)"),
        ]:
            candidate = base / "Eclipse" / "Sumo" / "bin" / "netconvert.exe"
            if candidate.exists():
                # Also set SUMO_HOME for downstream tools
                os.environ["SUMO_HOME"] = str(candidate.parent.parent)
                return str(candidate)

    # 3. Try pip-installed sumo_data package (ships binaries)
    try:
        import importlib.metadata as _meta
        dist = _meta.distribution("sumo-data")
        pkg_dir = Path(dist._path).parent  # type: ignore[attr-defined]
        # sumo-data installs binaries under <site-packages>/sumo/bin/
        for search_root in [pkg_dir / "sumo" / "bin", pkg_dir / "sumo_data" / "bin"]:
            candidate = search_root / ("netconvert.exe" if os.name == "nt" else "netconvert")
            if candidate.exists():
                return str(candidate)
    except (ImportError, AttributeError, TypeError):
        pass

    # 4. Walk the venv's site-packages for a netconvert binary
    for sp in sys.path:
        sp_path = Path(sp)
        if "site-packages" not in str(sp_path):
            continue
        for candidate in sp_path.rglob("netconvert*"):
            if candidate.is_file() and (candidate.suffix in ("", ".exe")):
                return str(candidate)

    raise FileNotFoundError(
        "netconvert not found. Install SUMO or set SUMO_HOME."
    )


def main() -> None:
    script_dir = Path(__file__).resolve().parent

    nod_file = script_dir / "corridor.nod.xml"
    edg_file = script_dir / "corridor.edg.xml"
    tll_file = script_dir / "corridor.tll.xml"
    out_file = script_dir / "corridor.net.xml"

    for f in (nod_file, edg_file, tll_file):
        if not f.exists():
            print(f"ERROR: Missing input file: {f}", file=sys.stderr)
            sys.exit(1)

    netconvert = find_netconvert()
    print(f"Using netconvert: {netconvert}")

    cmd = [
        netconvert,
        "--node-files", str(nod_file),
        "--edge-files", str(edg_file),
        "--tllogic-files", str(tll_file),
        "--output-file", str(out_file),
        "--no-turnarounds", "true",
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        print(f"\nERROR: netconvert exited with code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)

    if out_file.exists():
        size_kb = out_file.stat().st_size / 1024
        print(f"\nSUCCESS: {out_file.name} generated ({size_kb:.1f} KB)")
    else:
        print(f"\nERROR: {out_file.name} was not created", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
