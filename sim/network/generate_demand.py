#!/usr/bin/env python3
"""Generate heterogeneous Indian mixed-traffic demand and SUMO configuration.

Produces:
    sim/network/routes.rou.xml   – vTypes, routes, flows, and ambulance vehicle
    sim/network/corridor.sumocfg – SUMO config with SL2015 sublane model
"""

from __future__ import annotations

from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Indian mixed-traffic vehicle type definitions (sublane-compatible)
# ---------------------------------------------------------------------------
_VTYPES = """\
    <vType id="motorcycle"     length="2.0"  width="0.7"  maxSpeed="13.9"
           accel="2.6" decel="4.5" sigma="0.7" minGap="1.0"
           latAlignment="compact" lcSublane="1.0"/>
    <vType id="auto_rickshaw"  length="2.6"  width="1.35" maxSpeed="11.1"
           accel="1.8" decel="3.5" sigma="0.6" minGap="1.5"
           latAlignment="compact" lcSublane="0.8"/>
    <vType id="car"            length="4.5"  width="1.8"  maxSpeed="13.9"
           accel="2.0" decel="4.0" sigma="0.5" minGap="2.0"/>
    <vType id="bus"            length="11.0" width="2.5"  maxSpeed="10.0"
           accel="1.0" decel="3.0" sigma="0.4" minGap="3.0"/>
    <vType id="ambulance"      length="6.0"  width="2.1"  maxSpeed="16.7"
           accel="2.5" decel="5.0" sigma="0.3" minGap="2.0"
           vClass="emergency" color="255,0,0"/>
"""

# ---------------------------------------------------------------------------
# Route definitions
# ---------------------------------------------------------------------------
_ROUTES = """\
    <!-- Eastbound arterial through-corridor -->
    <route id="eb_through" edges="W_to_A A_to_B B_to_C C_to_E"/>
    <!-- Westbound arterial through-corridor -->
    <route id="wb_through" edges="E_to_C C_to_B B_to_A A_to_W"/>

    <!-- J_A cross-street -->
    <route id="ja_ns" edges="AN_to_A A_to_AS"/>
    <route id="ja_sn" edges="AS_to_A A_to_AN"/>

    <!-- J_B cross-street (heavy congestion target) -->
    <route id="jb_ns" edges="BN_to_B B_to_BS"/>
    <route id="jb_sn" edges="BS_to_B B_to_BN"/>

    <!-- J_C cross-street -->
    <route id="jc_ns" edges="CN_to_C C_to_CS"/>
    <route id="jc_sn" edges="CS_to_C C_to_CN"/>
"""

# ---------------------------------------------------------------------------
# Flow definitions – heavy congestion around J_B
# ---------------------------------------------------------------------------
_FLOWS = """\
    <!-- ============================================================ -->
    <!-- EASTBOUND ARTERIAL – heavy Indian mixed flow from West entry  -->
    <!-- ============================================================ -->
    <flow id="eb_moto"  type="motorcycle"    route="eb_through"
          begin="0" end="180" period="2.0"  departLane="free" departSpeed="max"/>
    <flow id="eb_auto"  type="auto_rickshaw" route="eb_through"
          begin="0" end="180" period="4.0"  departLane="free" departSpeed="max"/>
    <flow id="eb_car"   type="car"           route="eb_through"
          begin="0" end="180" period="2.5"  departLane="free" departSpeed="max"/>
    <flow id="eb_bus"   type="bus"           route="eb_through"
          begin="0" end="150" period="18.0" departLane="free" departSpeed="max"/>

    <!-- ============================================================ -->
    <!-- WESTBOUND ARTERIAL – moderate counter-flow                    -->
    <!-- ============================================================ -->
    <flow id="wb_moto"  type="motorcycle" route="wb_through"
          begin="0" end="180" period="6.0" departLane="free" departSpeed="max"/>
    <flow id="wb_car"   type="car"        route="wb_through"
          begin="0" end="180" period="7.0" departLane="free" departSpeed="max"/>

    <!-- ============================================================ -->
    <!-- J_B CROSS-STREET – heavy competing demand (causes congestion) -->
    <!-- ============================================================ -->
    <flow id="jb_ns_moto" type="motorcycle" route="jb_ns"
          begin="0" end="200" period="3.0" departLane="free" departSpeed="max"/>
    <flow id="jb_ns_auto" type="auto_rickshaw" route="jb_ns"
          begin="0" end="200" period="5.0" departLane="free" departSpeed="max"/>
    <flow id="jb_ns_car"  type="car" route="jb_ns"
          begin="0" end="200" period="4.0" departLane="free" departSpeed="max"/>
    <flow id="jb_sn_moto" type="motorcycle" route="jb_sn"
          begin="0" end="200" period="3.5" departLane="free" departSpeed="max"/>
    <flow id="jb_sn_car"  type="car" route="jb_sn"
          begin="0" end="200" period="4.5" departLane="free" departSpeed="max"/>

    <!-- ============================================================ -->
    <!-- J_A and J_C CROSS-STREETS – moderate background traffic       -->
    <!-- ============================================================ -->
    <flow id="ja_ns_car"  type="car"        route="ja_ns"
          begin="0" end="180" period="8.0"  departLane="free" departSpeed="max"/>
    <flow id="ja_sn_moto" type="motorcycle" route="ja_sn"
          begin="0" end="180" period="7.0"  departLane="free" departSpeed="max"/>
    <flow id="ja_sn_car"  type="car"        route="ja_sn"
          begin="0" end="180" period="10.0" departLane="free" departSpeed="max"/>
    <flow id="jc_ns_car"  type="car"        route="jc_ns"
          begin="0" end="180" period="9.0"  departLane="free" departSpeed="max"/>
    <flow id="jc_sn_car"  type="car"        route="jc_sn"
          begin="0" end="180" period="9.0"  departLane="free" departSpeed="max"/>
    <flow id="jc_ns_moto" type="motorcycle" route="jc_ns"
          begin="0" end="180" period="7.0"  departLane="free" departSpeed="max"/>

    <!-- ============================================================ -->
    <!-- AMBULANCE – dispatched at t=35 s, eastbound through corridor  -->
    <!-- ============================================================ -->
    <vehicle id="ambulance_0" type="ambulance" depart="35"
             departLane="best" departSpeed="max">
        <route edges="W_to_A A_to_B B_to_C C_to_E"/>
    </vehicle>
"""


def generate_routes(output_dir: Path | None = None) -> Path:
    """Write routes.rou.xml with Indian mixed-traffic demand."""
    out_dir = output_dir or _SCRIPT_DIR
    rou_path = out_dir / "routes.rou.xml"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        '        xsi:noNamespaceSchemaLocation='
        '"http://sumo.dlr.de/xsd/routes_file.xsd">\n'
        f"{_VTYPES}\n{_ROUTES}\n{_FLOWS}\n"
        "</routes>\n"
    )
    rou_path.write_text(xml, encoding="utf-8")
    print(f"  Written: {rou_path}  ({rou_path.stat().st_size / 1024:.1f} KB)")
    return rou_path


def generate_sumocfg(output_dir: Path | None = None) -> Path:
    """Write corridor.sumocfg with SL2015 sublane model (lateral-resolution 0.8)."""
    out_dir = output_dir or _SCRIPT_DIR
    cfg_path = out_dir / "corridor.sumocfg"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<configuration>\n"
        "    <input>\n"
        '        <net-file value="corridor.net.xml"/>\n'
        '        <route-files value="routes.rou.xml"/>\n'
        "    </input>\n"
        "    <time>\n"
        '        <begin value="0"/>\n'
        '        <end value="300"/>\n'
        "    </time>\n"
        "    <processing>\n"
        '        <lateral-resolution value="0.8"/>\n'
        "    </processing>\n"
        "    <report>\n"
        '        <no-step-log value="true"/>\n'
        '        <no-warnings value="true"/>\n'
        "    </report>\n"
        "</configuration>\n"
    )
    cfg_path.write_text(xml, encoding="utf-8")
    print(f"  Written: {cfg_path}")
    return cfg_path


def main() -> None:
    """Generate all demand files for the AegisFlow corridor scenario."""
    print("Generating Indian mixed-traffic demand …")
    generate_routes()
    generate_sumocfg()
    print("Done.")


if __name__ == "__main__":
    main()
