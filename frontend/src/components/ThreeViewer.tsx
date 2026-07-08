import { useRef, useEffect, type ElementRef } from "react";
import { useTranslation } from "react-i18next";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls, Grid, Text, Box, Cylinder, PerspectiveCamera } from "@react-three/drei";
import * as THREE from "three";
import { useStore } from "../store/useStore";
import { ROOM_COLORS, SEVERITY_COLORS } from "./roomColors";
import { floorRooms, roomsBBox, clampPos } from "./planGeometry";
import { PlanView2D } from "./PlanView2D";
import type { RoomLayout, MEPConflict, DoorSpec, WindowSpec } from "../types";

const FLOOR_HEIGHT = 3.0;
const WALL_HEIGHT = 3.0;
const SLAB_H = 0.15;

function RoomMesh({
  room,
  selected,
  onClick,
}: {
  room: RoomLayout;
  selected: boolean;
  onClick: () => void;
}) {
  const color = ROOM_COLORS[room.room_type] || "#607080";
  const z = (room.floor - 1) * FLOOR_HEIGHT;
  const wt = 0.12; // internal partition thickness (120mm); external wall is the building envelope

  return (
    <group
      position={[room.x + room.width / 2, z + SLAB_H / 2, room.y + room.depth / 2]}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
    >
      {/* Floor slab */}
      <Box args={[room.width, SLAB_H, room.depth]}>
        <meshStandardMaterial
          color={selected ? "#60a5fa" : "#2d3748"}
          roughness={0.9}
          metalness={0.0}
        />
      </Box>

      {/* 4 wall panels — open top so floor plan is visible from above */}
      {/* South wall */}
      <Box
        args={[room.width, WALL_HEIGHT, wt]}
        position={[0, WALL_HEIGHT / 2, -room.depth / 2 + wt / 2]}
      >
        <meshStandardMaterial
          color={color}
          roughness={0.85}
          metalness={0.05}
          side={THREE.DoubleSide}
        />
      </Box>
      {/* North wall */}
      <Box
        args={[room.width, WALL_HEIGHT, wt]}
        position={[0, WALL_HEIGHT / 2, room.depth / 2 - wt / 2]}
      >
        <meshStandardMaterial
          color={color}
          roughness={0.85}
          metalness={0.05}
          side={THREE.DoubleSide}
        />
      </Box>
      {/* West wall */}
      <Box
        args={[wt, WALL_HEIGHT, room.depth - wt * 2]}
        position={[-room.width / 2 + wt / 2, WALL_HEIGHT / 2, 0]}
      >
        <meshStandardMaterial
          color={color}
          roughness={0.85}
          metalness={0.05}
          side={THREE.DoubleSide}
        />
      </Box>
      {/* East wall */}
      <Box
        args={[wt, WALL_HEIGHT, room.depth - wt * 2]}
        position={[room.width / 2 - wt / 2, WALL_HEIGHT / 2, 0]}
      >
        <meshStandardMaterial
          color={color}
          roughness={0.85}
          metalness={0.05}
          side={THREE.DoubleSide}
        />
      </Box>

      {/* Doors */}
      {room.doors?.map((door, i) => (
        <DoorVisual key={`d${i}`} door={door} roomWidth={room.width} roomDepth={room.depth} />
      ))}

      {/* Windows */}
      {room.windows?.map((win, i) => (
        <WindowVisual key={`w${i}`} win={win} roomWidth={room.width} roomDepth={room.depth} />
      ))}

      {/* Room label */}
      <Text
        position={[0, 0.5, 0]}
        rotation={[-Math.PI / 2, 0, 0]}
        fontSize={0.35}
        color="#e2e8f0"
        anchorX="center"
        anchorY="middle"
        maxWidth={room.width - 0.2}
      >
        {`${room.name}\n${room.area_m2.toFixed(1)}m²`}
      </Text>
    </group>
  );
}

function DoorVisual({
  door,
  roomWidth,
  roomDepth,
}: {
  door: DoorSpec;
  roomWidth: number;
  roomDepth: number;
}) {
  const dh = door.height ?? 2.0;
  const dt = 0.12;
  const cy = SLAB_H / 2 + dh / 2; // center height above group origin
  const dw = door.width;
  const wallLen = door.wall === "S" || door.wall === "N" ? roomWidth : roomDepth;
  const dpos = clampPos(door.position, dw, wallLen);

  let pos: [number, number, number];
  let args: [number, number, number];
  if (door.wall === "S") {
    pos = [dpos + dw / 2 - roomWidth / 2, cy, -roomDepth / 2];
    args = [dw, dh, dt];
  } else if (door.wall === "N") {
    pos = [dpos + dw / 2 - roomWidth / 2, cy, roomDepth / 2];
    args = [dw, dh, dt];
  } else if (door.wall === "W") {
    pos = [-roomWidth / 2, cy, dpos + dw / 2 - roomDepth / 2];
    args = [dt, dh, dw];
  } else {
    pos = [roomWidth / 2, cy, dpos + dw / 2 - roomDepth / 2];
    args = [dt, dh, dw];
  }
  return (
    <Box args={args} position={pos}>
      <meshStandardMaterial color="#4a2c1a" roughness={0.7} />
    </Box>
  );
}

function WindowVisual({
  win,
  roomWidth,
  roomDepth,
}: {
  win: WindowSpec;
  roomWidth: number;
  roomDepth: number;
}) {
  const dt = 0.08;
  const cy = SLAB_H / 2 + win.sill + win.height / 2;
  const ww = win.width;
  const wh = win.height;
  const wallLen = win.wall === "S" || win.wall === "N" ? roomWidth : roomDepth;
  const wpos = clampPos(win.position, ww, wallLen);

  let pos: [number, number, number];
  let frameArgs: [number, number, number];
  let glassArgs: [number, number, number];
  if (win.wall === "S") {
    pos = [wpos + ww / 2 - roomWidth / 2, cy, -roomDepth / 2];
    frameArgs = [ww + 0.08, wh + 0.08, dt + 0.02];
    glassArgs = [ww, wh, dt];
  } else if (win.wall === "N") {
    pos = [wpos + ww / 2 - roomWidth / 2, cy, roomDepth / 2];
    frameArgs = [ww + 0.08, wh + 0.08, dt + 0.02];
    glassArgs = [ww, wh, dt];
  } else if (win.wall === "W") {
    pos = [-roomWidth / 2, cy, wpos + ww / 2 - roomDepth / 2];
    frameArgs = [dt + 0.02, wh + 0.08, ww + 0.08];
    glassArgs = [dt, wh, ww];
  } else {
    pos = [roomWidth / 2, cy, wpos + ww / 2 - roomDepth / 2];
    frameArgs = [dt + 0.02, wh + 0.08, ww + 0.08];
    glassArgs = [dt, wh, ww];
  }
  return (
    <group position={pos}>
      <Box args={frameArgs}>
        <meshStandardMaterial color="#e8e8e8" roughness={0.3} />
      </Box>
      <Box args={glassArgs}>
        <meshStandardMaterial
          color="#87CEEB"
          transparent
          opacity={0.4}
          metalness={0.1}
          roughness={0.05}
        />
      </Box>
    </group>
  );
}

function HumanMannequin({ position }: { position: [number, number, number] }) {
  return (
    <group position={position}>
      {/* Body */}
      <Cylinder args={[0.2, 0.2, 1.1, 8]} position={[0, 0.9, 0]}>
        <meshStandardMaterial color="#94a3b8" roughness={0.7} />
      </Cylinder>
      {/* Head */}
      <Box args={[0.3, 0.3, 0.3]} position={[0, 1.65, 0]}>
        <meshStandardMaterial color="#cbd5e1" roughness={0.7} />
      </Box>
      {/* Legs */}
      <Cylinder args={[0.1, 0.1, 0.8, 8]} position={[-0.12, 0.4, 0]}>
        <meshStandardMaterial color="#94a3b8" roughness={0.7} />
      </Cylinder>
      <Cylinder args={[0.1, 0.1, 0.8, 8]} position={[0.12, 0.4, 0]}>
        <meshStandardMaterial color="#94a3b8" roughness={0.7} />
      </Cylinder>
      {/* Height label */}
      <Text position={[0.5, 1.0, 0]} fontSize={0.2} color="#64748b" anchorX="left">
        1.8m
      </Text>
    </group>
  );
}

function ConflictMarker({ conflict }: { conflict: MEPConflict }) {
  const meshRef = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (meshRef.current) {
      (meshRef.current.material as THREE.MeshStandardMaterial).opacity =
        0.5 + 0.5 * Math.sin(clock.elapsedTime * 3);
    }
  });

  const color = SEVERITY_COLORS[conflict.severity] ?? SEVERITY_COLORS.MEDIUM;

  return (
    <mesh
      ref={meshRef}
      position={[conflict.location_x, conflict.location_z + 0.5, conflict.location_y]}
    >
      <sphereGeometry args={[0.25, 8, 8]} />
      <meshStandardMaterial
        color={color}
        transparent
        opacity={0.8}
        emissive={color}
        emissiveIntensity={0.5}
      />
    </mesh>
  );
}

// Moves orbit target and camera to the centroid of the current floor on each generation
function CameraRig() {
  const controlsRef = useRef<ElementRef<typeof OrbitControls>>(null);
  const { camera } = useThree();
  const { result, activeFloor } = useStore();

  useEffect(() => {
    if (!result || !controlsRef.current) return;
    // Plan Y maps to Three.js Z (depth axis).
    const bb = roomsBBox(floorRooms(result, activeFloor));
    if (!bb) return;

    const cx = (bb.minX + bb.maxX) / 2;
    const cz = (bb.minY + bb.maxY) / 2;
    const span = Math.max(bb.maxX - bb.minX, bb.maxY - bb.minY);
    const dist = span * 1.1 + 8;
    const fy = (activeFloor - 1) * FLOOR_HEIGHT + 1.5;

    controlsRef.current.target.set(cx, fy, cz);
    camera.position.set(cx + dist, fy + dist * 0.7, cz + dist);
    controlsRef.current.update();
    // Recenter only on a new generation (project_id) or floor change — not on
    // every camera move, so the user's manual orbit/zoom is preserved.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result?.project_id, activeFloor]);

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enablePan
      enableZoom
      enableRotate
      minPolarAngle={0}
      maxPolarAngle={Math.PI / 2.1}
      dampingFactor={0.05}
      enableDamping
    />
  );
}

function Scene() {
  const { result, activeFloor, showMEP, selectedRoomId, setSelectedRoom } = useStore();

  if (!result) return null;

  const visibleRooms = result.rooms.filter((r) => r.floor === activeFloor);

  // Centroid for mannequin placement
  const cx = visibleRooms.length
    ? visibleRooms.reduce((s, r) => s + r.x + r.width / 2, 0) / visibleRooms.length
    : 0;
  const cy = visibleRooms.length
    ? visibleRooms.reduce((s, r) => s + r.y + r.depth / 2, 0) / visibleRooms.length + 2
    : 2;
  const cz = (activeFloor - 1) * FLOOR_HEIGHT;

  return (
    <>
      {visibleRooms.map((room) => (
        <RoomMesh
          key={room.room_id}
          room={room}
          selected={selectedRoomId === room.room_id}
          onClick={() => setSelectedRoom(room.room_id === selectedRoomId ? null : room.room_id)}
        />
      ))}

      <HumanMannequin position={[cx, cz, cy]} />

      {showMEP &&
        result.mep_conflicts.map((c) => <ConflictMarker key={c.conflict_id} conflict={c} />)}
    </>
  );
}

export function ThreeViewer() {
  const { t } = useTranslation();
  const { result, activeFloor, setActiveFloor, showMEP, toggleMEP, viewMode, setViewMode } =
    useStore();
  const maxFloor = result ? Math.max(...result.rooms.map((r) => r.floor)) : 1;

  // 3D view is hidden for now. The 3D <Canvas> below is kept; restore the
  // switcher by uncommenting the "3d" entry here.
  const VIEW_MODES: { mode: "3d" | "2d"; label: string }[] = [
    // { mode: "3d", label: "3D" },
    { mode: "2d", label: t("viewer.plan2d") },
  ];

  return (
    <div className="relative w-full h-full min-h-[400px]">
      {viewMode === "3d" ? (
        <Canvas shadows gl={{ logarithmicDepthBuffer: true }}>
          <PerspectiveCamera makeDefault position={[15, 12, 15]} fov={45} />
          <ambientLight intensity={0.4} />
          <directionalLight
            castShadow
            position={[10, 20, 10]}
            intensity={1.5}
            shadow-mapSize={[2048, 2048]}
          />
          <pointLight position={[-10, 10, -10]} intensity={0.5} color="#6080ff" />

          <Grid
            infiniteGrid
            cellSize={1}
            cellThickness={0.3}
            sectionSize={5}
            sectionThickness={0.8}
            cellColor="#1e293b"
            sectionColor="#334155"
            fadeDistance={40}
            position={[0, -0.01, 0]}
          />

          <Scene />
          <CameraRig />
        </Canvas>
      ) : (
        <PlanView2D />
      )}

      {/* 2D / 3D view toggle — 3D is HIDDEN (its code below is kept, not deleted);
          re-add `{ mode: "3d" as const, label: "3D" }` to VIEW_MODES to restore it. */}
      {result && VIEW_MODES.length > 1 && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 flex bg-surface-card border border-surface-border rounded-lg p-0.5 shadow-lg z-10">
          {VIEW_MODES.map(({ mode, label }) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-all ${
                viewMode === mode
                  ? "bg-brand-600 text-white"
                  : "text-slate-500 hover:text-slate-800"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {/* Floor selector */}
      {result && maxFloor > 1 && (
        <div className="absolute top-4 left-4 flex flex-col gap-1">
          {Array.from({ length: maxFloor }, (_, i) => i + 1)
            .reverse()
            .map((f) => (
              <button
                key={f}
                onClick={() => setActiveFloor(f)}
                className={`w-9 h-9 rounded-lg text-sm font-semibold transition-all ${
                  activeFloor === f
                    ? "bg-brand-600 text-white"
                    : "bg-surface-card text-slate-500 hover:bg-surface-border"
                }`}
              >
                {f}
              </button>
            ))}
          <span className="text-xs text-slate-600 text-center mt-1">{t("viewer.floor")}</span>
        </div>
      )}

      {/* MEP toggle */}
      {result && (
        <div className="absolute top-4 right-4 flex flex-col gap-2">
          <button
            onClick={toggleMEP}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${
              showMEP
                ? "bg-red-50 border-red-300 text-red-700"
                : "bg-surface-card border-surface-border text-slate-500"
            }`}
          >
            {showMEP ? t("viewer.mepOn") : t("viewer.mepOff")}
          </button>
          {result.mep_conflicts.length > 0 && showMEP && (
            <span className="text-xs text-red-600 text-center">
              {t("viewer.clashes", { count: result.mep_conflicts.length })}
            </span>
          )}
        </div>
      )}

      {/* Legend — solid card: translucent bg interleaved with the SVG scale
          bar underneath made both unreadable. */}
      {result && (
        <div className="absolute bottom-4 left-4 card p-2 text-xs space-y-1">
          {viewMode === "2d" && (
            <>
              <div className="flex items-center gap-2">
                <span className="w-3 h-0.5 bg-amber-400 rounded" />
                <span>{t("viewer.door")}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-0.5 bg-sky-300 rounded" />
                <span>{t("viewer.window")}</span>
              </div>
              <div className="flex items-center gap-2">
                <svg viewBox="0 0 16 16" className="w-3.5 h-3.5 flex-shrink-0">
                  <circle cx="8" cy="8" r="3" fill="#f59e0b" />
                  {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => {
                    const a = (i * Math.PI) / 4;
                    return (
                      <line
                        key={i}
                        x1={8 + Math.cos(a) * 5}
                        y1={8 + Math.sin(a) * 5}
                        x2={8 + Math.cos(a) * 7}
                        y2={8 + Math.sin(a) * 7}
                        stroke="#f59e0b"
                        strokeWidth="1.2"
                        strokeLinecap="round"
                      />
                    );
                  })}
                </svg>
                <span>{t("viewer.daylight")}</span>
              </div>
              {showMEP && (
                <div className="flex items-center gap-2">
                  <svg viewBox="0 0 16 16" className="w-3.5 h-3.5 flex-shrink-0">
                    <line
                      x1="2"
                      y1="8"
                      x2="14"
                      y2="8"
                      stroke="#0891b2"
                      strokeWidth="1.2"
                      strokeDasharray="2 1.5"
                    />
                    <circle cx="8" cy="8" r="3" fill="#fff" stroke="#0891b2" strokeWidth="1.2" />
                    <circle cx="8" cy="8" r="1" fill="#0891b2" />
                  </svg>
                  <span>{t("viewer.mepDraft")}</span>
                </div>
              )}
            </>
          )}
          {/* Conflict swatches only when conflicts actually exist — otherwise the
              legend implies problems the plan doesn't have. */}
          {result.mep_conflicts.length > 0 && (
            <>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-red-500" />
                <span>{t("viewer.clashHigh")}</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-amber-500" />
                <span>{t("viewer.clashMedium")}</span>
              </div>
            </>
          )}
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-blue-400 rounded" />
            <span>{t("viewer.selectedRoom")}</span>
          </div>
        </div>
      )}
    </div>
  );
}
