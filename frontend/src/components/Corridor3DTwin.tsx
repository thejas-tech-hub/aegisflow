import { useEffect, useRef, useState } from "react";
import { Box, Camera, Compass, Eye, LocateFixed } from "lucide-react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import type {
  ABFrameSnapshot,
  ApiPulsePacket,
  JunctionID,
  SignalPhase,
} from "../types/telemetry";

interface Corridor3DTwinProps {
  frame: ABFrameSnapshot | null;
}

type CameraPresetId = "overview" | "follow_aegis" | "follow_baseline" | "jb_chokepoint";

const JUNCTION_ORDER: readonly JunctionID[] = ["J_A", "J_B", "J_C"];
const JUNCTION_METERS: Record<JunctionID, number> = {
  J_A: 0,
  J_B: 300,
  J_C: 600,
};

// Map corridor meters (-200..750) to centered 3D world X coordinates.
const WORLD_SCALE = 0.2;
const CORRIDOR_CENTER_M = 250;
const Z_BASELINE = -13.5;
const Z_AEGISFLOW = 13.5;
const ROAD_WIDTH = 7.6;
const STOP_LINE_OFFSET = 3.6;
const MAX_VEHICLES_PER_CLASS = 180;

function metersToWorldX(meters: number): number {
  return (meters - CORRIDOR_CENTER_M) * WORLD_SCALE;
}

function phaseToArterialColor(phase: SignalPhase): number {
  if (phase === "EW_GREEN") {
    return 0x10b981;
  }
  if (phase === "EW_YELLOW") {
    return 0xf59e0b;
  }
  return 0xf43f5e;
}

function phaseToCrossColor(phase: SignalPhase): number {
  if (phase === "NS_GREEN") {
    return 0x10b981;
  }
  if (phase === "NS_YELLOW") {
    return 0xf59e0b;
  }
  return 0xf43f5e;
}

function createSignalGlowTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Unable to create the intersection signal glow texture.");
  }
  const gradient = context.createRadialGradient(64, 64, 2, 64, 64, 62);
  gradient.addColorStop(0, "rgba(255,255,255,0.72)");
  gradient.addColorStop(0.28, "rgba(255,255,255,0.36)");
  gradient.addColorStop(0.68, "rgba(255,255,255,0.08)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, canvas.width, canvas.height);
  return new THREE.CanvasTexture(canvas);
}

function createWindowTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 256;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Unable to create the city window texture.");
  }
  context.fillStyle = "#0b132b";
  context.fillRect(0, 0, canvas.width, canvas.height);
  for (let row = 0; row < 16; row += 1) {
    for (let column = 0; column < 7; column += 1) {
      const lit = (row * 11 + column * 7) % 9 < 3;
      if (lit) {
        context.fillStyle =
          (row + column) % 4 === 0
            ? "rgba(93,143,190,0.34)"
            : "rgba(84,116,157,0.24)";
        context.fillRect(8 + column * 17, 7 + row * 15, 7, 8);
      }
    }
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

interface GantryRig {
  ewLensMat: THREE.MeshStandardMaterial;
  nsLensMat: THREE.MeshStandardMaterial;
  groundPoolMat: THREE.MeshBasicMaterial;
  heatMat: THREE.MeshBasicMaterial;
  heatMesh: THREE.Mesh;
  displayQueueM: number;
}

interface AmbulanceRig {
  group: THREE.Group;
  redBeaconMat: THREE.MeshStandardMaterial;
  blueBeaconMat: THREE.MeshStandardMaterial;
  haloMat: THREE.MeshBasicMaterial;
  halo: THREE.Mesh;
  radarRing: THREE.Mesh;
  radarMat: THREE.MeshBasicMaterial;
  trapBeacon: THREE.Mesh;
  trapMat: THREE.MeshBasicMaterial;
  displayX: number;
}

interface ApiArcRig {
  from: JunctionID;
  to: JunctionID;
  curve: THREE.CatmullRomCurve3;
  tubeMat: THREE.MeshStandardMaterial;
  orbs: THREE.Mesh[];
  orbMat: THREE.MeshStandardMaterial;
}

function createAmbulanceRig(accentHex: number): AmbulanceRig {
  const group = new THREE.Group();

  const bodyGeo = new THREE.BoxGeometry(2.8, 1.05, 1.25);
  const bodyMat = new THREE.MeshStandardMaterial({
    color: 0xf8fafc,
    roughness: 0.3,
    metalness: 0.25,
  });
  const body = new THREE.Mesh(bodyGeo, bodyMat);
  body.position.set(-0.2, 0.72, 0);
  group.add(body);

  const cabGeo = new THREE.BoxGeometry(1.0, 0.78, 1.18);
  const cab = new THREE.Mesh(cabGeo, bodyMat);
  cab.position.set(1.45, 0.58, 0);
  group.add(cab);

  const windshieldGeo = new THREE.BoxGeometry(0.08, 0.46, 1.02);
  const windshieldMat = new THREE.MeshStandardMaterial({
    color: 0x10213a,
    emissive: 0x071426,
    roughness: 0.18,
    metalness: 0.55,
  });
  const windshield = new THREE.Mesh(windshieldGeo, windshieldMat);
  windshield.position.set(1.97, 0.77, 0);
  group.add(windshield);

  const stripeGeo = new THREE.BoxGeometry(2.85, 0.22, 1.28);
  const stripeMat = new THREE.MeshStandardMaterial({
    color: 0xef4444,
    emissive: 0x991b1b,
    emissiveIntensity: 0.65,
    roughness: 0.35,
  });
  const stripe = new THREE.Mesh(stripeGeo, stripeMat);
  stripe.position.set(-0.2, 0.68, 0);
  group.add(stripe);

  const underGeo = new THREE.BoxGeometry(3.2, 0.08, 1.35);
  const underMat = new THREE.MeshBasicMaterial({
    color: accentHex,
    transparent: true,
    opacity: 0.65,
  });
  const under = new THREE.Mesh(underGeo, underMat);
  under.position.set(0.1, 0.14, 0);
  group.add(under);

  const podGeo = new THREE.BoxGeometry(0.32, 0.22, 0.48);
  const redBeaconMat = new THREE.MeshStandardMaterial({
    color: 0xff1744,
    emissive: 0xff1744,
    emissiveIntensity: 2.8,
    roughness: 0.2,
  });
  const blueBeaconMat = new THREE.MeshStandardMaterial({
    color: 0x00e5ff,
    emissive: 0x00e5ff,
    emissiveIntensity: 0.3,
    roughness: 0.2,
  });
  const leftPod = new THREE.Mesh(podGeo, redBeaconMat);
  leftPod.position.set(0.65, 1.35, -0.32);
  const rightPod = new THREE.Mesh(podGeo, blueBeaconMat);
  rightPod.position.set(0.65, 1.35, 0.32);
  group.add(leftPod, rightPod);

  const coneGeo = new THREE.ConeGeometry(1.15, 5.2, 16, 1, true);
  coneGeo.rotateZ(Math.PI / 2);
  const coneMat = new THREE.MeshBasicMaterial({
    color: 0xe0f2fe,
    transparent: true,
    opacity: 0.18,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const leftHeadlight = new THREE.Mesh(coneGeo, coneMat);
  leftHeadlight.position.set(4.3, 0.48, -0.38);
  const rightHeadlight = new THREE.Mesh(coneGeo, coneMat);
  rightHeadlight.position.set(4.3, 0.48, 0.38);
  group.add(leftHeadlight, rightHeadlight);

  const radarGeo = new THREE.RingGeometry(1.6, 2.05, 32);
  radarGeo.rotateX(-Math.PI / 2);
  const radarMat = new THREE.MeshBasicMaterial({
    color: accentHex,
    transparent: true,
    opacity: 0.75,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const radarRing = new THREE.Mesh(radarGeo, radarMat);
  radarRing.position.set(0.2, 0.09, 0);
  group.add(radarRing);

  const haloGeo = new THREE.RingGeometry(2.22, 2.36, 48);
  haloGeo.rotateX(-Math.PI / 2);
  const haloMat = new THREE.MeshBasicMaterial({
    color: accentHex,
    transparent: true,
    opacity: 0.52,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    toneMapped: false,
    side: THREE.DoubleSide,
  });
  const halo = new THREE.Mesh(haloGeo, haloMat);
  halo.position.set(0.2, 0.105, 0);
  group.add(halo);

  const trapGeo = new THREE.CylinderGeometry(2.1, 2.1, 5.4, 24, 1, true);
  const trapMat = new THREE.MeshBasicMaterial({
    color: 0xf43f5e,
    transparent: true,
    opacity: 0.0,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const trapBeacon = new THREE.Mesh(trapGeo, trapMat);
  trapBeacon.position.set(0.1, 2.75, 0);
  trapBeacon.visible = false;
  group.add(trapBeacon);

  return {
    group,
    redBeaconMat,
    blueBeaconMat,
    haloMat,
    halo,
    radarRing,
    radarMat,
    trapBeacon,
    trapMat,
    displayX: metersToWorldX(-180),
  };
}

function buildRoadway(
  scene: THREE.Scene,
  trackZ: number,
  curbHex: number
): Record<JunctionID, GantryRig> {
  const roadLength = 220;
  const roadCenterX = 5;

  const roadGeo = new THREE.BoxGeometry(roadLength, 0.12, ROAD_WIDTH);
  const roadMat = new THREE.MeshStandardMaterial({
    color: 0x0d1628,
    roughness: 0.85,
    metalness: 0.2,
  });
  const roadMesh = new THREE.Mesh(roadGeo, roadMat);
  roadMesh.position.set(roadCenterX, 0.02, trackZ);
  scene.add(roadMesh);

  const curbGeo = new THREE.BoxGeometry(roadLength, 0.18, 0.2);
  const curbMat = new THREE.MeshStandardMaterial({
    color: curbHex,
    emissive: curbHex,
    emissiveIntensity: curbHex === 0x22d3ee ? 1.45 : 0.9,
    roughness: 0.25,
  });
  const northCurb = new THREE.Mesh(curbGeo, curbMat);
  northCurb.position.set(roadCenterX, 0.09, trackZ - ROAD_WIDTH / 2 - 0.12);
  const southCurb = new THREE.Mesh(curbGeo, curbMat);
  southCurb.position.set(roadCenterX, 0.09, trackZ + ROAD_WIDTH / 2 + 0.12);
  scene.add(northCurb, southCurb);

  // Crisp bright dashed road dividers
  const dashCount = 44;
  const dashGeo = new THREE.PlaneGeometry(2.5, 0.2);
  dashGeo.rotateX(-Math.PI / 2);
  const dashMat = new THREE.MeshBasicMaterial({
    color: 0x94a3b8,
    transparent: true,
    opacity: 0.65,
  });
  const dashInst = new THREE.InstancedMesh(dashGeo, dashMat, dashCount);
  const dummy = new THREE.Object3D();
  for (let i = 0; i < dashCount; i += 1) {
    dummy.position.set(-100 + i * 4.9, 0.095, trackZ);
    dummy.updateMatrix();
    dashInst.setMatrixAt(i, dummy.matrix);
  }
  dashInst.instanceMatrix.needsUpdate = true;
  scene.add(dashInst);

  const rigs = {} as Record<JunctionID, GantryRig>;
  const crossGeo = new THREE.BoxGeometry(6.8, 0.1, 17.0);
  const crossMat = new THREE.MeshStandardMaterial({
    color: 0x0b1324,
    roughness: 0.88,
  });
  const stopLineGeo = new THREE.PlaneGeometry(0.36, ROAD_WIDTH - 0.5);
  stopLineGeo.rotateX(-Math.PI / 2);
  const stopLineMat = new THREE.MeshBasicMaterial({
    color: 0xf1f5f9,
    transparent: true,
    opacity: 0.92,
  });
  const pillarGeo = new THREE.CylinderGeometry(0.16, 0.2, 5.4, 10);
  const beamGeo = new THREE.BoxGeometry(0.45, 0.4, ROAD_WIDTH + 2.0);
  const steelMat = new THREE.MeshStandardMaterial({
    color: 0x26354d,
    metalness: 0.65,
    roughness: 0.35,
  });
  const lensGeo = new THREE.SphereGeometry(0.44, 16, 16);
  const poolGeo = new THREE.CircleGeometry(4.8, 28);
  poolGeo.rotateX(-Math.PI / 2);
  const signalGlowTexture = createSignalGlowTexture();
  const crosswalkGeo = new THREE.BoxGeometry(0.42, 0.035, ROAD_WIDTH - 0.9);
  const crosswalkMat = new THREE.MeshBasicMaterial({
    color: 0xe2e8f0,
    transparent: true,
    opacity: 0.76,
    depthWrite: false,
  });

  for (const jid of JUNCTION_ORDER) {
    const jx = metersToWorldX(JUNCTION_METERS[jid]);

    const crossMesh = new THREE.Mesh(crossGeo, crossMat);
    crossMesh.position.set(jx, 0.01, trackZ);
    scene.add(crossMesh);

    const stripeCount = 9;
    const crosswalk = new THREE.InstancedMesh(
      crosswalkGeo,
      crosswalkMat,
      stripeCount
    );
    for (let stripe = 0; stripe < stripeCount; stripe += 1) {
      const stripeTransform = new THREE.Object3D();
      stripeTransform.position.set(
        jx - 3.2 + stripe * 0.8,
        0.095,
        trackZ
      );
      stripeTransform.updateMatrix();
      crosswalk.setMatrixAt(stripe, stripeTransform.matrix);
    }
    crosswalk.instanceMatrix.needsUpdate = true;
    scene.add(crosswalk);

    const stopLine = new THREE.Mesh(stopLineGeo, stopLineMat);
    stopLine.position.set(jx - STOP_LINE_OFFSET, 0.098, trackZ);
    scene.add(stopLine);

    const leftPillar = new THREE.Mesh(pillarGeo, steelMat);
    leftPillar.position.set(jx - 3.2, 2.7, trackZ - ROAD_WIDTH / 2 - 0.8);
    const rightPillar = new THREE.Mesh(pillarGeo, steelMat);
    rightPillar.position.set(jx - 3.2, 2.7, trackZ + ROAD_WIDTH / 2 + 0.8);
    const topBeam = new THREE.Mesh(beamGeo, steelMat);
    topBeam.position.set(jx - 3.2, 5.35, trackZ);
    scene.add(leftPillar, rightPillar, topBeam);

    const ewLensMat = new THREE.MeshStandardMaterial({
      color: 0xf43f5e,
      emissive: 0xf43f5e,
      emissiveIntensity: 2.5,
      roughness: 0.2,
    });
    const nsLensMat = new THREE.MeshStandardMaterial({
      color: 0x10b981,
      emissive: 0x10b981,
      emissiveIntensity: 2.3,
      roughness: 0.2,
    });
    const ewLens = new THREE.Mesh(lensGeo, ewLensMat);
    ewLens.position.set(jx - 3.2, 5.05, trackZ - 1.2);
    const nsLens = new THREE.Mesh(lensGeo, nsLensMat);
    nsLens.position.set(jx - 3.2, 5.05, trackZ + 1.2);
    scene.add(ewLens, nsLens);

    const groundPoolMat = new THREE.MeshBasicMaterial({
      color: 0xf43f5e,
      map: signalGlowTexture,
      transparent: true,
      opacity: 0.42,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      toneMapped: false,
    });
    const groundPool = new THREE.Mesh(poolGeo, groundPoolMat);
    groundPool.position.set(jx, 0.115, trackZ);
    scene.add(groundPool);

    const heatGeo = new THREE.BoxGeometry(1.0, 0.45, ROAD_WIDTH + 0.45);
    const heatMat = new THREE.MeshBasicMaterial({
      color: 0xf59e0b,
      transparent: true,
      opacity: 0.0,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const heatMesh = new THREE.Mesh(heatGeo, heatMat);
    heatMesh.position.set(jx - STOP_LINE_OFFSET - 5, 0.25, trackZ);
    heatMesh.visible = false;
    scene.add(heatMesh);

    rigs[jid] = {
      ewLensMat,
      nsLensMat,
      groundPoolMat,
      heatMat,
      heatMesh,
      displayQueueM: 0,
    };
  }

  return rigs;
}

function buildCitySkyline(scene: THREE.Scene): void {
  const windowsTexture = createWindowTexture();
  const glassMat = new THREE.MeshStandardMaterial({
    color: 0x0b132b,
    map: windowsTexture,
    emissive: 0x243b5a,
    emissiveMap: windowsTexture,
    emissiveIntensity: 0.38,
    roughness: 0.25,
    metalness: 0.6,
  });
  const rimMat = new THREE.LineBasicMaterial({
    color: 0x50658a,
    transparent: true,
    opacity: 0.22,
    depthWrite: false,
  });

  const footprints: Array<{ x: number; z: number; w: number; h: number; d: number }> = [];
  for (let i = 0; i < 16; i += 1) {
    const x = -92 + i * 13.5;
    const nearJunction =
      Math.abs(x + 50) < 6.5 || Math.abs(x - 10) < 6.5 || Math.abs(x - 70) < 6.5;
    if (nearJunction) {
      continue;
    }
    const backHeight = 7 + ((i * 7) % 14);
    footprints.push({
      x,
      z: Z_BASELINE - 15 - ((i % 3) * 4),
      w: 6.5,
      h: backHeight,
      d: 7.0,
    });
    const frontHeight = 2.5 + ((i * 3) % 4.5);
    footprints.push({
      x: x + 2.0,
      z: Z_AEGISFLOW + 17 + ((i % 2) * 3.5),
      w: 5.5,
      h: frontHeight,
      d: 5.5,
    });
  }

  for (const fp of footprints) {
    const geo = new THREE.BoxGeometry(fp.w, fp.h, fp.d);
    const mesh = new THREE.Mesh(geo, glassMat);
    mesh.position.set(fp.x, fp.h / 2, fp.z);
    scene.add(mesh);

    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo), rimMat);
    edges.position.copy(mesh.position);
    scene.add(edges);
  }
}

function createApiArcs(scene: THREE.Scene): ApiArcRig[] {
  const pairs: Array<{ from: JunctionID; to: JunctionID }> = [
    { from: "J_A", to: "J_B" },
    { from: "J_B", to: "J_C" },
  ];

  const orbGeo = new THREE.SphereGeometry(0.42, 14, 14);
  return pairs.map(({ from, to }) => {
    const x1 = metersToWorldX(JUNCTION_METERS[from]);
    const x2 = metersToWorldX(JUNCTION_METERS[to]);
    const midX = (x1 + x2) / 2;

    const curve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(x1, 5.4, Z_AEGISFLOW),
      new THREE.Vector3((x1 + midX) / 2, 12.2, Z_AEGISFLOW),
      new THREE.Vector3(midX, 14.5, Z_AEGISFLOW),
      new THREE.Vector3((midX + x2) / 2, 12.2, Z_AEGISFLOW),
      new THREE.Vector3(x2, 5.4, Z_AEGISFLOW),
    ]);

    const tubeGeo = new THREE.TubeGeometry(curve, 44, 0.15, 8, false);
    const tubeMat = new THREE.MeshStandardMaterial({
      color: 0x22d3ee,
      emissive: 0x22d3ee,
      emissiveIntensity: 0.3,
      transparent: true,
      opacity: 0.18,
      roughness: 0.25,
    });
    const tube = new THREE.Mesh(tubeGeo, tubeMat);
    scene.add(tube);

    const orbMat = new THREE.MeshStandardMaterial({
      color: 0x67e8f9,
      emissive: 0x22d3ee,
      emissiveIntensity: 3.0,
      roughness: 0.1,
    });
    const orbs = [0, 1, 2].map(() => {
      const orb = new THREE.Mesh(orbGeo, orbMat);
      orb.visible = false;
      scene.add(orb);
      return orb;
    });

    return { from, to, curve, tubeMat, orbs, orbMat };
  });
}

function resolvePresetPose(
  preset: CameraPresetId,
  aegisEvX: number,
  baseEvX: number
): { pos: THREE.Vector3; target: THREE.Vector3 } {
  switch (preset) {
    case "follow_aegis":
      return {
        pos: new THREE.Vector3(aegisEvX - 20, 15, Z_AEGISFLOW + 24),
        target: new THREE.Vector3(aegisEvX + 8, 1.5, Z_AEGISFLOW),
      };
    case "follow_baseline":
      return {
        pos: new THREE.Vector3(baseEvX - 18, 16, Z_BASELINE + 26),
        target: new THREE.Vector3(baseEvX + 6, 1.5, Z_BASELINE),
      };
    case "jb_chokepoint":
      return {
        pos: new THREE.Vector3(24, 21, 38),
        target: new THREE.Vector3(2, 1.2, 0),
      };
    default:
      return {
        pos: new THREE.Vector3(8, 42, 70),
        target: new THREE.Vector3(8, 0.5, 0),
      };
  }
}

export function Corridor3DTwin({ frame }: Corridor3DTwinProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const latestFrameRef = useRef<ABFrameSnapshot | null>(frame);
  const presetRef = useRef<CameraPresetId>("overview");
  const transitionActiveRef = useRef<boolean>(false);

  // Refs for 60 FPS CSS2D world-projected labels (zero React re-renders)
  const labelJaRef = useRef<HTMLDivElement | null>(null);
  const labelJbRef = useRef<HTMLDivElement | null>(null);
  const labelJcRef = useRef<HTMLDivElement | null>(null);

  // Refs for live 3D XYZ gizmo SVG lines
  const axisXLineRef = useRef<SVGLineElement | null>(null);
  const axisYLineRef = useRef<SVGLineElement | null>(null);
  const axisZLineRef = useRef<SVGLineElement | null>(null);
  const axisXTextRef = useRef<SVGTextElement | null>(null);
  const axisYTextRef = useRef<SVGTextElement | null>(null);
  const axisZTextRef = useRef<SVGTextElement | null>(null);

  const [cameraPreset, setCameraPreset] = useState<CameraPresetId>("overview");

  useEffect(() => {
    latestFrameRef.current = frame;
  }, [frame]);

  const handleSelectPreset = (nextPreset: CameraPresetId): void => {
    presetRef.current = nextPreset;
    transitionActiveRef.current = true;
    setCameraPreset(nextPreset);
  };

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    let viewportW = Math.max(container.clientWidth, 320);
    let viewportH = Math.max(container.clientHeight, 320);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x030712);
    scene.fog = new THREE.FogExp2(0x030712, 0.0038);

    const camera = new THREE.PerspectiveCamera(45, viewportW / viewportH, 0.5, 420);
    camera.position.set(8, 42, 70);

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      powerPreference: "high-performance",
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(viewportW, viewportH);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.08;
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.07;
    controls.maxPolarAngle = Math.PI * 0.465;
    controls.minDistance = 12;
    controls.maxDistance = 185;
    controls.target.set(8, 0.5, 0);

    const onControlStart = (): void => {
      transitionActiveRef.current = false;
    };
    controls.addEventListener("start", onControlStart);

    // Brightened night-sky lighting for crisp dark-mode contrast
    const ambient = new THREE.AmbientLight(0x273652, 1.55);
    const hemi = new THREE.HemisphereLight(0x38bdf8, 0x040712, 1.05);
    const moon = new THREE.DirectionalLight(0xe2e8f0, 1.75);
    moon.position.set(-40, 80, 50);
    scene.add(ambient, hemi, moon);

    const composer = new EffectComposer(renderer);
    const renderPass = new RenderPass(scene, camera);
    const bloomPass = new UnrealBloomPass(
      new THREE.Vector2(viewportW, viewportH),
      0.65,
      0.45,
      0.65
    );
    const outputPass = new OutputPass();
    composer.addPass(renderPass);
    composer.addPass(bloomPass);
    composer.addPass(outputPass);

    // Ground cyber-grid + dark matte floor
    const groundGeo = new THREE.PlaneGeometry(340, 220);
    groundGeo.rotateX(-Math.PI / 2);
    const groundMat = new THREE.MeshStandardMaterial({
      color: 0x030712,
      roughness: 0.94,
      metalness: 0.08,
    });
    const groundMesh = new THREE.Mesh(groundGeo, groundMat);
    groundMesh.position.set(8, -0.08, 0);
    scene.add(groundMesh);

    const grid = new THREE.GridHelper(280, 56, 0x1e40af, 0x0f172a);
    grid.position.set(8, -0.04, 0);
    scene.add(grid);

    buildCitySkyline(scene);

    const baselineRigs = buildRoadway(scene, Z_BASELINE, 0xe11d48);
    const aegisflowRigs = buildRoadway(scene, Z_AEGISFLOW, 0x22d3ee);

    const baseAmbulance = createAmbulanceRig(0xf43f5e);
    const aegisAmbulance = createAmbulanceRig(0x22d3ee);
    scene.add(baseAmbulance.group, aegisAmbulance.group);

    const apiArcs = createApiArcs(scene);

    // Heterogeneous Traffic InstancedMeshes
    const motoGeo = new THREE.BoxGeometry(0.95, 0.55, 0.42);
    const motoMat = new THREE.MeshStandardMaterial({
      color: 0x38bdf8,
      roughness: 0.4,
      metalness: 0.4,
    });
    const autoGeo = new THREE.BoxGeometry(1.2, 0.82, 0.7);
    const autoMat = new THREE.MeshStandardMaterial({
      color: 0xfacc15,
      roughness: 0.42,
      metalness: 0.25,
    });
    const carGeo = new THREE.BoxGeometry(1.85, 0.72, 0.95);
    const carMat = new THREE.MeshStandardMaterial({
      color: 0xe2e8f0,
      roughness: 0.32,
      metalness: 0.5,
    });
    const busGeo = new THREE.BoxGeometry(4.1, 1.32, 1.16);
    const busMat = new THREE.MeshStandardMaterial({
      color: 0xfb923c,
      roughness: 0.48,
      metalness: 0.25,
    });
    const brakeGeo = new THREE.BoxGeometry(0.08, 0.16, 0.62);
    const brakeMat = new THREE.MeshStandardMaterial({
      color: 0xff1e42,
      emissive: 0xff1e42,
      emissiveIntensity: 2.3,
      roughness: 0.2,
    });
    const roofGeo = new THREE.BoxGeometry(0.78, 0.24, 0.62);
    const roofMat = new THREE.MeshStandardMaterial({
      color: 0x10243b,
      emissive: 0x071a2c,
      emissiveIntensity: 0.55,
      roughness: 0.22,
      metalness: 0.55,
    });
    const headlightGeo = new THREE.BoxGeometry(0.14, 0.12, 0.18);
    const headlightMat = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      emissive: 0xe0f2fe,
      emissiveIntensity: 3.2,
      roughness: 0.15,
    });

    const motoInst = new THREE.InstancedMesh(motoGeo, motoMat, MAX_VEHICLES_PER_CLASS);
    const autoInst = new THREE.InstancedMesh(autoGeo, autoMat, MAX_VEHICLES_PER_CLASS);
    const carInst = new THREE.InstancedMesh(carGeo, carMat, MAX_VEHICLES_PER_CLASS);
    const busInst = new THREE.InstancedMesh(busGeo, busMat, MAX_VEHICLES_PER_CLASS);
    const roofInst = new THREE.InstancedMesh(
      roofGeo,
      roofMat,
      MAX_VEHICLES_PER_CLASS * 4
    );
    const headlightInst = new THREE.InstancedMesh(
      headlightGeo,
      headlightMat,
      MAX_VEHICLES_PER_CLASS * 8
    );
    const brakeInst = new THREE.InstancedMesh(
      brakeGeo,
      brakeMat,
      MAX_VEHICLES_PER_CLASS * 4
    );

    motoInst.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    autoInst.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    carInst.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    busInst.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    roofInst.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    headlightInst.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    brakeInst.instanceMatrix.setUsage(THREE.DynamicDrawUsage);

    scene.add(motoInst, autoInst, carInst, busInst, roofInst, headlightInst, brakeInst);

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = Math.floor(entry.contentRect.width);
        const h = Math.floor(entry.contentRect.height);
        if (w > 0 && h > 0) {
          viewportW = w;
          viewportH = h;
          camera.aspect = w / h;
          camera.updateProjectionMatrix();
          renderer.setSize(w, h);
          composer.setSize(w, h);
          bloomPass.setSize(w, h);
        }
      }
    });
    resizeObserver.observe(container);

    const dummy = new THREE.Object3D();
    const zeroScale = new THREE.Vector3(0, 0, 0);
    const unitScale = new THREE.Vector3(1, 1, 1);

    const projVec = new THREE.Vector3();
    const invQuat = new THREE.Quaternion();
    const axisXVec = new THREE.Vector3();
    const axisYVec = new THREE.Vector3();
    const axisZVec = new THREE.Vector3();

    const anchorTargets: Array<{
      ref: { readonly current: HTMLDivElement | null };
      worldPos: THREE.Vector3;
    }> = [
      {
        ref: labelJaRef,
        worldPos: new THREE.Vector3(metersToWorldX(0), 9.85, 0),
      },
      {
        ref: labelJbRef,
        worldPos: new THREE.Vector3(metersToWorldX(300), 9.85, 0),
      },
      {
        ref: labelJcRef,
        worldPos: new THREE.Vector3(metersToWorldX(600), 9.85, 0),
      },
    ];

    let rafId = 0;
    let lastTime = performance.now();

    const animate = (now: number): void => {
      rafId = window.requestAnimationFrame(animate);
      const dt = Math.min(0.08, Math.max(0.001, (now - lastTime) / 1000));
      lastTime = now;
      const elapsedS = now / 1000;
      const smoothAlpha = 1 - Math.exp(-8 * dt);

      const snapshot = latestFrameRef.current;

      let motoCount = 0;
      let autoCount = 0;
      let carCount = 0;
      let busCount = 0;
      let roofCount = 0;
      let headlightCount = 0;
      let brakeCount = 0;

      const addVehicleCabAndLights = (
        kind: "moto" | "auto" | "car" | "bus",
        x: number,
        z: number,
        bodyY: number
      ): void => {
        const dimensions = {
          moto: { length: 0.95, width: 0.42, roofY: 0.65 },
          auto: { length: 1.2, width: 0.7, roofY: 0.9 },
          car: { length: 1.85, width: 0.95, roofY: 0.84 },
          bus: { length: 4.1, width: 1.16, roofY: 1.48 },
        }[kind];
        if (roofCount < MAX_VEHICLES_PER_CLASS * 4) {
          dummy.position.set(x + dimensions.length * 0.08, dimensions.roofY, z);
          dummy.scale.set(
            dimensions.length / 1.3,
            1,
            dimensions.width / 0.7
          );
          dummy.updateMatrix();
          roofInst.setMatrixAt(roofCount, dummy.matrix);
          roofCount += 1;
        }
        for (const side of [-1, 1]) {
          if (headlightCount >= MAX_VEHICLES_PER_CLASS * 8) {
            break;
          }
          dummy.position.set(
            x + dimensions.length / 2 - 0.08,
            bodyY,
            z + side * dimensions.width * 0.3
          );
          dummy.scale.copy(unitScale);
          dummy.updateMatrix();
          headlightInst.setMatrixAt(headlightCount, dummy.matrix);
          headlightCount += 1;
        }
      };

      const appendVehicle = (
        kind: "moto" | "auto" | "car" | "bus",
        x: number,
        z: number
      ): void => {
        if (kind === "moto" && motoCount < MAX_VEHICLES_PER_CLASS) {
          dummy.position.set(x, 0.36, z);
          dummy.scale.copy(unitScale);
          dummy.updateMatrix();
          motoInst.setMatrixAt(motoCount, dummy.matrix);
          motoCount += 1;
          addVehicleCabAndLights(kind, x, z, 0.36);
          if (brakeCount < MAX_VEHICLES_PER_CLASS * 4) {
            dummy.position.set(x - 0.5, 0.35, z);
            dummy.updateMatrix();
            brakeInst.setMatrixAt(brakeCount, dummy.matrix);
            brakeCount += 1;
          }
        } else if (kind === "auto" && autoCount < MAX_VEHICLES_PER_CLASS) {
          dummy.position.set(x, 0.5, z);
          dummy.scale.copy(unitScale);
          dummy.updateMatrix();
          autoInst.setMatrixAt(autoCount, dummy.matrix);
          autoCount += 1;
          addVehicleCabAndLights(kind, x, z, 0.5);
          if (brakeCount < MAX_VEHICLES_PER_CLASS * 4) {
            dummy.position.set(x - 0.63, 0.45, z);
            dummy.updateMatrix();
            brakeInst.setMatrixAt(brakeCount, dummy.matrix);
            brakeCount += 1;
          }
        } else if (kind === "car" && carCount < MAX_VEHICLES_PER_CLASS) {
          dummy.position.set(x, 0.44, z);
          dummy.scale.copy(unitScale);
          dummy.updateMatrix();
          carInst.setMatrixAt(carCount, dummy.matrix);
          carCount += 1;
          addVehicleCabAndLights(kind, x, z, 0.55);
          if (brakeCount < MAX_VEHICLES_PER_CLASS * 4) {
            dummy.position.set(x - 0.96, 0.44, z);
            dummy.updateMatrix();
            brakeInst.setMatrixAt(brakeCount, dummy.matrix);
            brakeCount += 1;
          }
        } else if (kind === "bus" && busCount < MAX_VEHICLES_PER_CLASS) {
          dummy.position.set(x, 0.74, z);
          dummy.scale.copy(unitScale);
          dummy.updateMatrix();
          busInst.setMatrixAt(busCount, dummy.matrix);
          busCount += 1;
          addVehicleCabAndLights(kind, x, z, 0.8);
          if (brakeCount < MAX_VEHICLES_PER_CLASS * 4) {
            dummy.position.set(x - 2.08, 0.56, z);
            dummy.updateMatrix();
            brakeInst.setMatrixAt(brakeCount, dummy.matrix);
            brakeCount += 1;
          }
        }
      };

      const updateTrackVisuals = (
        rigs: Record<JunctionID, GantryRig>,
        states: ABFrameSnapshot["baseline"]["states"],
        trackZ: number
      ): void => {
        const sublanes = [trackZ - 2.1, trackZ, trackZ + 2.1];
        for (const jid of JUNCTION_ORDER) {
          const rig = rigs[jid];
          const pkt = states[jid];

          const ewColor = phaseToArterialColor(pkt.active_phase);
          const nsColor = phaseToCrossColor(pkt.active_phase);
          rig.ewLensMat.color.setHex(ewColor);
          rig.ewLensMat.emissive.setHex(ewColor);
          rig.nsLensMat.color.setHex(nsColor);
          rig.nsLensMat.emissive.setHex(nsColor);
          rig.groundPoolMat.color.setHex(ewColor);

          rig.displayQueueM = THREE.MathUtils.lerp(
            rig.displayQueueM,
            pkt.queue_length_m,
            smoothAlpha
          );
          const queueWorldLen = Math.max(0, rig.displayQueueM * WORLD_SCALE);
          const stopLineX = metersToWorldX(JUNCTION_METERS[jid]) - STOP_LINE_OFFSET;

          const occ = pkt.spatial_occupancy_ratio;
          if (occ >= 0.58 && queueWorldLen > 2) {
            rig.heatMesh.visible = true;
            rig.heatMesh.scale.x = queueWorldLen;
            rig.heatMesh.position.x = stopLineX - queueWorldLen / 2;
            const pulse = occ >= 0.78 ? 0.38 + 0.22 * Math.sin(elapsedS * 5) : 0.22;
            rig.heatMat.color.setHex(occ >= 0.78 ? 0xf43f5e : 0xf59e0b);
            rig.heatMat.opacity = pulse;
          } else {
            rig.heatMesh.visible = false;
          }

          if (queueWorldLen > 1.2) {
            const mix = pkt.vehicle_mix;
            const totalMix = Math.max(
              1,
              mix.motorcycles + mix.auto_rickshaws + mix.cars + mix.buses_trucks
            );
            const motoShare = mix.motorcycles / totalMix;
            const autoShare = mix.auto_rickshaws / totalMix;
            const carShare = mix.cars / totalMix;

            const laneOffsets = [1.4, 2.2, 1.8];
            for (let laneIdx = 0; laneIdx < sublanes.length; laneIdx += 1) {
              let cursor = laneOffsets[laneIdx];
              let step = 0;
              while (cursor < queueWorldLen - 0.8) {
                const selector = ((step * 0.37 + laneIdx * 0.23) % 1 + 1) % 1;
                let kind: "moto" | "auto" | "car" | "bus" = "bus";
                let spacing = 4.9;
                if (selector < motoShare) {
                  kind = "moto";
                  spacing = 1.8;
                } else if (selector < motoShare + autoShare) {
                  kind = "auto";
                  spacing = 2.2;
                } else if (selector < motoShare + autoShare + carShare) {
                  kind = "car";
                  spacing = 2.9;
                }
                const worldX = stopLineX - cursor - spacing * 0.45;
                appendVehicle(kind, worldX, sublanes[laneIdx]);
                cursor += spacing;
                step += 1;
              }
            }
          }
        }
      };

      const updateAmbulance = (
        rig: AmbulanceRig,
        posM: number,
        trapped: boolean,
        trackZ: number
      ): void => {
        const targetX = metersToWorldX(posM);
        rig.displayX = THREE.MathUtils.lerp(rig.displayX, targetX, smoothAlpha);
        rig.group.position.set(rig.displayX, 0, trackZ);

        const flashPhase = Math.floor(elapsedS * 8) % 2 === 0;
        rig.redBeaconMat.emissiveIntensity = flashPhase ? 3.2 : 0.25;
        rig.blueBeaconMat.emissiveIntensity = flashPhase ? 0.25 : 3.2;

        const radarProgress = (elapsedS * 0.9) % 1;
        const scale = 1 + radarProgress * 2.1;
        rig.radarRing.scale.set(scale, 1, scale);
        rig.radarMat.opacity = (1 - radarProgress) * 0.7;

        if (trapped) {
          rig.trapBeacon.visible = true;
          rig.trapMat.opacity = 0.28 + 0.22 * Math.sin(elapsedS * 6.5);
          const pulseScale = 1 + 0.14 * Math.sin(elapsedS * 6.5);
          rig.trapBeacon.scale.set(pulseScale, 1, pulseScale);
        } else {
          rig.trapBeacon.visible = false;
        }
      };

      const updateApiArcs = (pulses: ApiPulsePacket[]): void => {
        for (const arc of apiArcs) {
          const matching = pulses.find(
            (p) =>
              (p.from === arc.from && p.to === arc.to) ||
              (p.from === arc.to && p.to === arc.from)
          );
          if (matching) {
            const isBackpressure =
              matching.type === "SPILLBACK_METERING_BACKPRESSURE";
            const hex = isBackpressure ? 0xf59e0b : 0x22d3ee;
            arc.tubeMat.color.setHex(hex);
            arc.tubeMat.emissive.setHex(hex);
            arc.tubeMat.emissiveIntensity = 2.0;
            arc.tubeMat.opacity = 0.88;
            arc.orbMat.color.setHex(hex);
            arc.orbMat.emissive.setHex(hex);

            arc.orbs.forEach((orb, idx) => {
              orb.visible = true;
              const rawT = (elapsedS * 0.85 + idx / 3) % 1;
              const t = isBackpressure ? 1 - rawT : rawT;
              orb.position.copy(arc.curve.getPointAt(t));
            });
          } else {
            arc.tubeMat.color.setHex(0x22d3ee);
            arc.tubeMat.emissive.setHex(0x22d3ee);
            arc.tubeMat.emissiveIntensity = 0.25;
            arc.tubeMat.opacity = 0.16;
            for (const orb of arc.orbs) {
              orb.visible = false;
            }
          }
        }
      };

      if (snapshot !== null) {
        updateTrackVisuals(baselineRigs, snapshot.baseline.states, Z_BASELINE);
        updateTrackVisuals(aegisflowRigs, snapshot.aegisflow.states, Z_AEGISFLOW);

        updateAmbulance(
          baseAmbulance,
          snapshot.baseline.ev_position_m,
          snapshot.baseline.ev_trapped_in_spillback,
          Z_BASELINE
        );
        updateAmbulance(
          aegisAmbulance,
          snapshot.aegisflow.ev_position_m,
          snapshot.aegisflow.ev_trapped_in_spillback,
          Z_AEGISFLOW
        );

        updateApiArcs(snapshot.aegisflow.active_api_packets);
      } else {
        updateAmbulance(baseAmbulance, -180, false, Z_BASELINE);
        updateAmbulance(aegisAmbulance, -180, false, Z_AEGISFLOW);
        updateApiArcs([]);
      }

      motoInst.count = motoCount;
      autoInst.count = autoCount;
      carInst.count = carCount;
      busInst.count = busCount;
      roofInst.count = roofCount;
      headlightInst.count = headlightCount;
      brakeInst.count = brakeCount;
      if (motoCount > 0) motoInst.instanceMatrix.needsUpdate = true;
      if (autoCount > 0) autoInst.instanceMatrix.needsUpdate = true;
      if (carCount > 0) carInst.instanceMatrix.needsUpdate = true;
      if (busCount > 0) busInst.instanceMatrix.needsUpdate = true;
      if (roofCount > 0) roofInst.instanceMatrix.needsUpdate = true;
      if (headlightCount > 0) headlightInst.instanceMatrix.needsUpdate = true;
      if (brakeCount > 0) brakeInst.instanceMatrix.needsUpdate = true;
      if (motoCount === 0) {
        dummy.scale.copy(zeroScale);
        dummy.updateMatrix();
        motoInst.setMatrixAt(0, dummy.matrix);
      }

      const activePreset = presetRef.current;
      const isFollowMode =
        activePreset === "follow_aegis" || activePreset === "follow_baseline";
      if (transitionActiveRef.current || isFollowMode) {
        const pose = resolvePresetPose(
          activePreset,
          aegisAmbulance.displayX,
          baseAmbulance.displayX
        );
        const camAlpha = 1 - Math.exp(-4.5 * dt);
        camera.position.lerp(pose.pos, camAlpha);
        controls.target.lerp(pose.target, camAlpha);
        if (
          !isFollowMode &&
          camera.position.distanceTo(pose.pos) < 0.25 &&
          controls.target.distanceTo(pose.target) < 0.25
        ) {
          transitionActiveRef.current = false;
        }
      }

      controls.update();
      camera.updateMatrixWorld();

      // Keep projected junction tags visible and clear of the viewport edges.
      for (const anchor of anchorTargets) {
        const el = anchor.ref.current;
        if (!el) {
          continue;
        }
        projVec.copy(anchor.worldPos).project(camera);
        if (projVec.z >= 1 || projVec.z <= -1) {
          el.style.opacity = "0";
          continue;
        }
        const projectedX = (projVec.x * 0.5 + 0.5) * viewportW;
        const projectedY = (-projVec.y * 0.5 + 0.5) * viewportH;
        const px = THREE.MathUtils.clamp(
          projectedX,
          el.offsetWidth / 2 + 8,
          viewportW - el.offsetWidth / 2 - 8
        );
        const py = THREE.MathUtils.clamp(projectedY, 20, viewportH - 20);
        el.style.opacity = "1";
        el.style.transform = `translate3d(${px.toFixed(1)}px, ${py.toFixed(1)}px, 0) translate(-50%, -50%)`;
      }

      // Update live 3D XYZ gizmo SVG orientation
      invQuat.copy(camera.quaternion).invert();
      axisXVec.set(1, 0, 0).applyQuaternion(invQuat);
      axisYVec.set(0, 1, 0).applyQuaternion(invQuat);
      axisZVec.set(0, 0, 1).applyQuaternion(invQuat);
      const cx = 28;
      const cy = 28;
      const r = 18;

      if (axisXLineRef.current && axisXTextRef.current) {
        const x2 = cx + axisXVec.x * r;
        const y2 = cy - axisXVec.y * r;
        axisXLineRef.current.setAttribute("x2", x2.toFixed(1));
        axisXLineRef.current.setAttribute("y2", y2.toFixed(1));
        axisXTextRef.current.setAttribute("x", (cx + axisXVec.x * (r + 7)).toFixed(1));
        axisXTextRef.current.setAttribute("y", (cy - axisXVec.y * (r + 7) + 3).toFixed(1));
      }
      if (axisYLineRef.current && axisYTextRef.current) {
        const x2 = cx + axisYVec.x * r;
        const y2 = cy - axisYVec.y * r;
        axisYLineRef.current.setAttribute("x2", x2.toFixed(1));
        axisYLineRef.current.setAttribute("y2", y2.toFixed(1));
        axisYTextRef.current.setAttribute("x", (cx + axisYVec.x * (r + 7)).toFixed(1));
        axisYTextRef.current.setAttribute("y", (cy - axisYVec.y * (r + 7) + 3).toFixed(1));
      }
      if (axisZLineRef.current && axisZTextRef.current) {
        const x2 = cx + axisZVec.x * r;
        const y2 = cy - axisZVec.y * r;
        axisZLineRef.current.setAttribute("x2", x2.toFixed(1));
        axisZLineRef.current.setAttribute("y2", y2.toFixed(1));
        axisZTextRef.current.setAttribute("x", (cx + axisZVec.x * (r + 7)).toFixed(1));
        axisZTextRef.current.setAttribute("y", (cy - axisZVec.y * (r + 7) + 3).toFixed(1));
      }

      composer.render();
    };

    rafId = window.requestAnimationFrame(animate);

    return () => {
      window.cancelAnimationFrame(rafId);
      resizeObserver.disconnect();
      controls.removeEventListener("start", onControlStart);
      controls.dispose();

      const disposedGeometries = new Set<THREE.BufferGeometry>();
      const disposedMaterials = new Set<THREE.Material>();
      const disposedTextures = new Set<THREE.Texture>();
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh || obj instanceof THREE.LineSegments) {
          if (!disposedGeometries.has(obj.geometry)) {
            disposedGeometries.add(obj.geometry);
            obj.geometry.dispose();
          }
          const disposeMaterial = (material: THREE.Material): void => {
            if (disposedMaterials.has(material)) {
              return;
            }
            disposedMaterials.add(material);
            const disposeTexture = (texture: THREE.Texture | null): void => {
              if (texture && !disposedTextures.has(texture)) {
                disposedTextures.add(texture);
                texture.dispose();
              }
            };
            if (material instanceof THREE.MeshStandardMaterial) {
              disposeTexture(material.map);
              disposeTexture(material.emissiveMap);
            } else if (material instanceof THREE.MeshBasicMaterial) {
              disposeTexture(material.map);
            }
            material.dispose();
          };
          if (Array.isArray(obj.material)) {
            for (const mat of obj.material) {
              disposeMaterial(mat);
            }
          } else {
            disposeMaterial(obj.material);
          }
        }
      });

      bloomPass.dispose();
      composer.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }
    };
  }, []);

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-800/90 bg-[#030712]">
      {/* WebGL Canvas */}
      <div
        ref={containerRef}
        className="h-[360px] min-h-0 w-full flex-1 sm:h-[395px] xl:h-full"
        aria-label="Interactive 3D Smart-City Corridor Digital Twin"
      />

      {/* World-Projected CSS2D Junction Labels */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div
          ref={labelJaRef}
          className="absolute left-0 top-0 whitespace-nowrap rounded-full border border-slate-700/80 bg-slate-950/85 px-2.5 py-0.5 font-mono text-[10px] font-semibold text-slate-200 shadow-lg backdrop-blur"
          style={{ opacity: 0 }}
        >
          J_A <span className="text-slate-400">· Entry · 0m</span>
        </div>
        <div
          ref={labelJbRef}
          className="absolute left-0 top-0 whitespace-nowrap rounded-full border border-amber-400/50 bg-slate-950/90 px-2.5 py-0.5 font-mono text-[10px] font-bold text-amber-300 shadow-[0_0_12px_rgba(245,158,11,0.22)] backdrop-blur"
          style={{ opacity: 0 }}
        >
          J_B <span className="text-amber-200/80">· Chokepoint · 300m</span>
        </div>
        <div
          ref={labelJcRef}
          className="absolute left-0 top-0 whitespace-nowrap rounded-full border border-slate-700/80 bg-slate-950/85 px-2.5 py-0.5 font-mono text-[10px] font-semibold text-slate-200 shadow-lg backdrop-blur"
          style={{ opacity: 0 }}
        >
          J_C <span className="text-slate-400">· Exit · 600m</span>
        </div>

      </div>

      <div className="pointer-events-none absolute bottom-3 left-3 flex flex-col gap-1.5">
        <span className="w-fit whitespace-nowrap rounded-lg border border-rose-500/45 bg-rose-950/85 px-2.5 py-1 font-sans text-[10px] font-bold tracking-wide text-rose-200 shadow-[0_0_12px_rgba(244,63,94,0.16)] backdrop-blur">
          TRACK A · BASELINE EVP
        </span>
        <span className="w-fit whitespace-nowrap rounded-lg border border-cyan-400/45 bg-cyan-950/85 px-2.5 py-1 font-sans text-[10px] font-bold tracking-wide text-cyan-200 shadow-[0_0_12px_rgba(34,211,238,0.16)] backdrop-blur">
          TRACK B · AEGISFLOW v2.0
        </span>
      </div>

      {/* Single-row camera preset toolbar */}
      <div className="pointer-events-auto absolute left-3 right-20 top-3">
        <div
          title="Drag to orbit · Scroll to zoom · Right-drag to pan"
          className="flex w-fit max-w-full flex-nowrap items-center gap-0.5 overflow-x-auto rounded-xl border border-slate-700/75 bg-slate-950/80 p-1 backdrop-blur-md"
        >
          <span className="inline-flex shrink-0 items-center gap-1 px-1.5 font-sans text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            <Camera className="h-3 w-3 text-cyan-400" />
            <span className="hidden sm:inline">Cam</span>
          </span>
          {(
            [
              { id: "overview", label: "Overview", icon: Compass },
              { id: "follow_aegis", label: "Aegis EV", icon: Eye },
              { id: "follow_baseline", label: "Baseline", icon: LocateFixed },
              { id: "jb_chokepoint", label: "J_B", icon: Box },
            ] as const
          ).map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => handleSelectPreset(id)}
              className={`inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-lg px-1.5 py-1 font-sans text-[9px] font-medium transition-colors sm:px-2 sm:text-[10px] ${
                cameraPreset === id
                  ? "bg-cyan-500/25 text-cyan-200 ring-1 ring-cyan-400/50"
                  : "text-slate-300 hover:bg-slate-800/80 hover:text-white"
              }`}
            >
              <Icon className="h-3 w-3" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Top-Right Compact 3D XYZ Axis Gizmo */}
      <div className="pointer-events-none absolute right-3 top-3 flex items-center justify-center rounded-xl border border-slate-700/70 bg-slate-950/75 p-1.5 backdrop-blur-md">
        <svg viewBox="0 0 56 56" className="h-12 w-12" aria-hidden="true">
          <line
            ref={axisXLineRef}
            x1="28"
            y1="28"
            x2="46"
            y2="28"
            stroke="#fb7185"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <text
            ref={axisXTextRef}
            x="51"
            y="31"
            fill="#fb7185"
            fontSize="9"
            fontWeight="700"
            textAnchor="middle"
            className="font-mono"
          >
            X
          </text>
          <line
            ref={axisYLineRef}
            x1="28"
            y1="28"
            x2="28"
            y2="10"
            stroke="#34d399"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <text
            ref={axisYTextRef}
            x="28"
            y="7"
            fill="#34d399"
            fontSize="9"
            fontWeight="700"
            textAnchor="middle"
            className="font-mono"
          >
            Y
          </text>
          <line
            ref={axisZLineRef}
            x1="28"
            y1="28"
            x2="16"
            y2="38"
            stroke="#38bdf8"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <text
            ref={axisZTextRef}
            x="11"
            y="44"
            fill="#38bdf8"
            fontSize="9"
            fontWeight="700"
            textAnchor="middle"
            className="font-mono"
          >
            Z
          </text>
        </svg>
      </div>

      {frame === null ? (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="rounded-xl border border-slate-800 bg-slate-950/85 px-5 py-3 font-sans text-xs text-cyan-300 backdrop-blur-md">
            3D Digital Twin Online — Awaiting WebSocket Telemetry Frame...
          </div>
        </div>
      ) : null}
    </div>
  );
}
