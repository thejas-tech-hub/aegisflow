"""TraCI bridge connecting SUMO microsimulation to AegisFlow contracts.

Launches SUMO (headless or GUI), reads per-junction telemetry each
1-second step, and applies safety-verified signal commands via
``traci.trafficlight.setPhase()``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

import traci  # type: ignore[import-untyped]

from schemas.contracts import (
    JunctionID,
    JunctionStatePacket,
    SignalPhase,
    VehicleMix,
    VerifiedSignalCommand,
)

# ---------------------------------------------------------------------------
# Phase index ⇄ SignalPhase mapping (matches corridor.tll.xml)
# ---------------------------------------------------------------------------
PHASE_INDEX_TO_SIGNAL: Final[dict[int, SignalPhase]] = {
    0: SignalPhase.NS_GREEN,
    1: SignalPhase.NS_YELLOW,
    2: SignalPhase.ALL_RED_TO_EW,
    3: SignalPhase.EW_GREEN,
    4: SignalPhase.EW_YELLOW,
    5: SignalPhase.ALL_RED_TO_NS,
}

SIGNAL_TO_PHASE_INDEX: Final[dict[SignalPhase, int]] = {
    v: k for k, v in PHASE_INDEX_TO_SIGNAL.items()
}

# ---------------------------------------------------------------------------
# Junction topology
# ---------------------------------------------------------------------------
INCOMING_EDGES: Final[dict[JunctionID, list[str]]] = {
    JunctionID.J_A: ["AN_to_A", "B_to_A", "AS_to_A", "W_to_A"],
    JunctionID.J_B: ["BN_to_B", "C_to_B", "BS_to_B", "A_to_B"],
    JunctionID.J_C: ["CN_to_C", "E_to_C", "CS_to_C", "B_to_C"],
}

# Arterial edges the ambulance traverses (upstream → downstream order).
_AMBULANCE_APPROACH: Final[dict[JunctionID, list[str]]] = {
    JunctionID.J_A: ["W_to_A"],
    JunctionID.J_B: ["W_to_A", "A_to_B"],
    JunctionID.J_C: ["W_to_A", "A_to_B", "B_to_C"],
}

# PCU weights per Indian vehicle class.
_PCU: Final[dict[str, float]] = {
    "motorcycle": 0.5,
    "auto_rickshaw": 1.0,
    "car": 1.0,
    "bus": 3.0,
    "ambulance": 1.2,
}

# Default lane width (m) and lane count per edge.
_LANE_WIDTH_M: float = 3.2
_LANES_PER_EDGE: int = 2

# Pre-computed edge lengths (from corridor.net.xml lane shapes).
_EDGE_LENGTH_M: Final[dict[str, float]] = {
    "W_to_A": 289.60,
    "A_to_W": 289.60,
    "A_to_B": 279.20,
    "B_to_A": 279.20,
    "B_to_C": 279.20,
    "C_to_B": 279.20,
    "C_to_E": 289.60,
    "E_to_C": 289.60,
    "AN_to_A": 239.60,
    "A_to_AN": 239.60,
    "AS_to_A": 239.60,
    "A_to_AS": 239.60,
    "BN_to_B": 239.60,
    "B_to_BN": 239.60,
    "BS_to_B": 239.60,
    "B_to_BS": 239.60,
    "CN_to_C": 239.60,
    "C_to_CN": 239.60,
    "CS_to_C": 239.60,
    "C_to_CS": 239.60,
}


def _find_sumo_binary(gui: bool) -> str:
    """Locate ``sumo`` or ``sumo-gui`` executable."""
    name = "sumo-gui" if gui else "sumo"

    # 1) Check SUMO_HOME
    sumo_home = os.environ.get("SUMO_HOME", "")
    if sumo_home:
        candidate = Path(sumo_home) / "bin" / f"{name}.exe"
        if candidate.is_file():
            return str(candidate)
        candidate = Path(sumo_home) / "bin" / name
        if candidate.is_file():
            return str(candidate)

    # 2) Common Windows install
    for base in [
        Path(r"C:\Program Files (x86)\SUMO"),
        Path(r"C:\Program Files\SUMO"),
    ]:
        candidate = base / "bin" / f"{name}.exe"
        if candidate.is_file():
            return str(candidate)

    # 3) Fallback: assume it's on PATH
    return name


class SUMOCorridorBridge:
    """Bidirectional interface between SUMO and AegisFlow contract layer."""

    def __init__(
        self,
        sumocfg_path: str,
        gui: bool = False,
        seed: int = 42,
    ) -> None:
        self._sumocfg = sumocfg_path
        self._gui = gui
        self._seed = seed
        self._binary = _find_sumo_binary(gui)

        # Internal tracking
        self._sim_time: float = 0.0
        self._phase_start_time: dict[JunctionID, float] = {
            jid: 0.0 for jid in JunctionID
        }
        self._current_phase: dict[JunctionID, int] = {
            jid: 0 for jid in JunctionID
        }
        self._prev_vehicles: dict[str, set[str]] = {}  # edge → vehicle IDs
        self._started = False

    # -----------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------

    def start(self) -> None:
        """Launch SUMO via TraCI."""
        cmd: list[str] = [
            self._binary,
            "-c",
            self._sumocfg,
            "--seed",
            str(self._seed),
            "--step-length",
            "1.0",
        ]
        traci.start(cmd)
        self._started = True

        # Initialise edge vehicle sets
        for jid in JunctionID:
            for edge in INCOMING_EDGES[jid]:
                self._prev_vehicles[edge] = set()

        # Read initial phases
        for jid in JunctionID:
            idx = traci.trafficlight.getPhase(jid.value)
            self._current_phase[jid] = idx
            self._phase_start_time[jid] = 0.0

    def close(self) -> None:
        """Shut down SUMO."""
        if self._started:
            try:
                traci.close()
            except traci.exceptions.FatalTraCIError:
                pass
            self._started = False

    # -----------------------------------------------------------------
    # Step: advance simulation + read telemetry
    # -----------------------------------------------------------------

    def step(self) -> dict[JunctionID, JunctionStatePacket]:
        """Advance SUMO by 1 s and emit per-junction state packets."""
        traci.simulationStep()
        self._sim_time = traci.simulation.getTime()

        states: dict[JunctionID, JunctionStatePacket] = {}
        for jid in JunctionID:
            states[jid] = self._read_junction(jid)
        return states

    def _read_junction(self, jid: JunctionID) -> JunctionStatePacket:
        """Compute all telemetry fields for one junction."""
        edges = INCOMING_EDGES[jid]

        # --- Phase tracking ---
        raw_phase = traci.trafficlight.getPhase(jid.value)
        if raw_phase != self._current_phase[jid]:
            self._current_phase[jid] = raw_phase
            self._phase_start_time[jid] = self._sim_time
        active_phase = PHASE_INDEX_TO_SIGNAL.get(raw_phase, SignalPhase.NS_GREEN)
        phase_elapsed = self._sim_time - self._phase_start_time[jid]

        # --- Vehicle-level metrics ---
        mix = VehicleMix()
        total_veh_area = 0.0
        total_road_area = 0.0
        pcu_total = 0.0
        speed_sum = 0.0
        veh_count = 0
        queue_length_m = 0.0

        current_vehicles: dict[str, set[str]] = {}
        total_inflow = 0
        total_outflow = 0

        # Ambulance detection
        ev_detected = False
        ev_distance_m: float | None = None
        ev_eta_s: float | None = None

        for edge_id in edges:
            edge_len = _EDGE_LENGTH_M.get(edge_id, 250.0)
            road_area = edge_len * _LANE_WIDTH_M * _LANES_PER_EDGE
            total_road_area += road_area

            veh_ids: list[str] = list(traci.edge.getLastStepVehicleIDs(edge_id))
            current_vehicles[edge_id] = set(veh_ids)

            # Inflow / outflow
            prev = self._prev_vehicles.get(edge_id, set())
            cur = current_vehicles[edge_id]
            total_inflow += len(cur - prev)
            total_outflow += len(prev - cur)

            for vid in veh_ids:
                vtype: str = traci.vehicle.getTypeID(vid)
                length: float = traci.vehicle.getLength(vid)
                width: float = traci.vehicle.getWidth(vid)
                speed: float = traci.vehicle.getSpeed(vid)
                pos: float = traci.vehicle.getLanePosition(vid)

                total_veh_area += length * width
                speed_sum += speed
                veh_count += 1

                # Vehicle mix classification
                if "motorcycle" in vtype:
                    mix.motorcycles += 1
                elif "auto_rickshaw" in vtype:
                    mix.auto_rickshaws += 1
                elif "bus" in vtype:
                    mix.buses_trucks += 1
                elif "ambulance" in vtype:
                    mix.emergency_vehicles += 1
                else:
                    mix.cars += 1

                # PCU
                pcu_total += _PCU.get(vtype, 1.0)

                # Queue: halting vehicles (speed < 1.0 m/s)
                if speed < 1.0:
                    dist_to_stop = edge_len - pos
                    queue_length_m = max(queue_length_m, dist_to_stop)

        # --- Spatial occupancy ---
        if total_road_area > 0:
            occupancy = min(1.0, max(0.0, total_veh_area / total_road_area))
        else:
            occupancy = 0.0

        avg_speed = speed_sum / veh_count if veh_count > 0 else 0.0

        # --- Ambulance detection (look at approach edges for this junction) ---
        approach_edges = _AMBULANCE_APPROACH[jid]
        ev_detected, ev_distance_m, ev_eta_s = self._detect_ambulance(
            jid, approach_edges
        )

        # Update prev_vehicles
        for edge_id in edges:
            self._prev_vehicles[edge_id] = current_vehicles.get(edge_id, set())

        return JunctionStatePacket(
            junction_id=jid,
            timestamp=self._sim_time,
            source="sumo",
            active_phase=active_phase,
            phase_elapsed_s=round(phase_elapsed, 2),
            spatial_occupancy_ratio=round(occupancy, 4),
            pcu_density=round(pcu_total, 2),
            queue_length_m=round(queue_length_m, 2),
            link_length_m=round(
                sum(_EDGE_LENGTH_M.get(e, 250.0) for e in edges), 2
            ),
            avg_speed_mps=round(avg_speed, 2),
            inflow_rate_vps=float(total_inflow),
            outflow_rate_vps=float(total_outflow),
            vehicle_mix=mix,
            ev_detected=ev_detected,
            ev_confidence=1.0 if ev_detected else 0.0,
            ev_eta_s=ev_eta_s,
            ev_distance_m=ev_distance_m,
        )

    def _detect_ambulance(
        self,
        jid: JunctionID,
        approach_edges: list[str],
    ) -> tuple[bool, float | None, float | None]:
        """Check if ``ambulance_0`` is approaching *jid* via upstream edges."""
        try:
            all_veh = traci.vehicle.getIDList()
        except traci.exceptions.TraCIException:
            return False, None, None

        if "ambulance_0" not in all_veh:
            return False, None, None

        amb_edge: str = traci.vehicle.getRoadID("ambulance_0")
        amb_pos: float = traci.vehicle.getLanePosition("ambulance_0")
        amb_speed: float = traci.vehicle.getSpeed("ambulance_0")

        if amb_edge not in approach_edges:
            return False, None, None

        # Distance = remaining on current edge + full lengths of edges in between
        edge_idx = approach_edges.index(amb_edge)
        edge_len = _EDGE_LENGTH_M.get(amb_edge, 250.0)
        distance = edge_len - amb_pos  # remaining on current edge

        # Add full lengths of edges between current edge and the junction's
        # direct incoming approach edge (last in the approach list)
        for subsequent_edge in approach_edges[edge_idx + 1 :]:
            distance += _EDGE_LENGTH_M.get(subsequent_edge, 250.0)

        eta = distance / amb_speed if amb_speed > 0.5 else distance / 0.5

        return True, round(distance, 2), round(eta, 2)

    # -----------------------------------------------------------------
    # Apply commands
    # -----------------------------------------------------------------

    def apply_commands(
        self,
        commands: dict[JunctionID, VerifiedSignalCommand],
    ) -> None:
        """Set SUMO traffic light phases from safety-verified commands."""
        for jid, cmd in commands.items():
            target_idx = SIGNAL_TO_PHASE_INDEX.get(cmd.approved_phase)
            if target_idx is None:
                continue
            current_idx = traci.trafficlight.getPhase(jid.value)
            if current_idx != target_idx:
                traci.trafficlight.setPhase(jid.value, target_idx)
                self._current_phase[jid] = target_idx
                self._phase_start_time[jid] = self._sim_time
            # Prevent SUMO from auto-advancing phase
            traci.trafficlight.setPhaseDuration(jid.value, 9999)

    @property
    def sim_time(self) -> float:
        """Current SUMO simulation time in seconds."""
        return self._sim_time
