import { memo, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useStore } from "../store/useStore";
import {
  ROOM_FILL_2D,
  DEFAULT_FILL_2D,
  SELECTION_COLOR,
  SELECTION_ACCENT,
  SEVERITY_COLORS,
} from "./roomColors";
import { floorRooms, roomsBBox, clampPos, type BBox } from "./planGeometry";
import type { RoomLayout, MEPConflict, DoorSpec, WindowSpec } from "../types";

const WALL_T = 0.18; // wall line thickness in plan units (m)
const PAD = 2.8; // sheet margin around the plan for dimension lines (m)
const BG = "#060b15";

interface VB {
  x: number;
  y: number;
  w: number;
  h: number;
}

function clampW(w: number) {
  return Math.min(Math.max(w, 2), 500);
}

// Scales the viewBox by k around the anchor point (ax, ay) in world coords
function zoomViewBox(v: VB, k: number, ax: number, ay: number): VB {
  const w = clampW(v.w * k);
  const s = w / v.w;
  return { x: ax - (ax - v.x) * s, y: ay - (ay - v.y) * s, w, h: v.h * s };
}

// fy flips plan Y so that north (larger y) points up on screen
type FlipFn = (y: number) => number;

function DoorSymbol({ room, door, fy }: { room: RoomLayout; door: DoorSpec; fy: FlipFn }) {
  const dw = door.width;
  let gap: { x1: number; y1: number; x2: number; y2: number };
  let leaf: { x1: number; y1: number; x2: number; y2: number };
  let arc: string;

  if (door.wall === "S" || door.wall === "N") {
    const x1 = room.x + clampPos(door.position, dw, room.width);
    const x2 = x1 + dw;
    const yw = door.wall === "S" ? fy(room.y) : fy(room.y + room.depth);
    const dir = door.wall === "S" ? -1 : 1; // into the room, in SVG y
    const sweep = door.wall === "S" ? 0 : 1;
    gap = { x1, y1: yw, x2, y2: yw };
    leaf = { x1, y1: yw, x2: x1, y2: yw + dir * dw };
    arc = `M ${x2} ${yw} A ${dw} ${dw} 0 0 ${sweep} ${x1} ${yw + dir * dw}`;
  } else {
    const dpos = clampPos(door.position, dw, room.depth);
    const yTop = fy(room.y + dpos + dw);
    const yBot = fy(room.y + dpos);
    const xw = door.wall === "W" ? room.x : room.x + room.width;
    const dir = door.wall === "W" ? 1 : -1; // into the room, in SVG x
    const sweep = door.wall === "W" ? 0 : 1;
    gap = { x1: xw, y1: yTop, x2: xw, y2: yBot };
    leaf = { x1: xw, y1: yTop, x2: xw + dir * dw, y2: yTop };
    arc = `M ${xw} ${yBot} A ${dw} ${dw} 0 0 ${sweep} ${xw + dir * dw} ${yTop}`;
  }

  return (
    <g pointerEvents="none">
      <line {...gap} stroke={BG} strokeWidth={WALL_T + 0.08} />
      <path d={arc} fill="none" stroke="#5d6f86" strokeWidth={0.03} />
      <line {...leaf} stroke="#d9a05b" strokeWidth={0.07} strokeLinecap="round" />
    </g>
  );
}

function WindowSymbol({ room, win, fy }: { room: RoomLayout; win: WindowSpec; fy: FlipFn }) {
  const ww = win.width;
  const t = 0.16; // frame depth on plan

  let x: number, y: number, w: number, h: number;
  let mid: { x1: number; y1: number; x2: number; y2: number };

  if (win.wall === "S" || win.wall === "N") {
    const x1 = room.x + clampPos(win.position, ww, room.width);
    const yw = win.wall === "S" ? fy(room.y) : fy(room.y + room.depth);
    x = x1;
    y = yw - t / 2;
    w = ww;
    h = t;
    mid = { x1, y1: yw, x2: x1 + ww, y2: yw };
  } else {
    const yTop = fy(room.y + clampPos(win.position, ww, room.depth) + ww);
    const xw = win.wall === "W" ? room.x : room.x + room.width;
    x = xw - t / 2;
    y = yTop;
    w = t;
    h = ww;
    mid = { x1: xw, y1: yTop, x2: xw, y2: yTop + ww };
  }

  return (
    <g pointerEvents="none">
      <line {...mid} stroke={BG} strokeWidth={WALL_T + 0.08} />
      <rect x={x} y={y} width={w} height={h} fill="#0b1726" stroke="#7dd3fc" strokeWidth={0.035} />
      <line {...mid} stroke="#7dd3fc" strokeWidth={0.025} />
    </g>
  );
}

function RoomLabel({ room, fy, selected }: { room: RoomLayout; fy: FlipFn; selected: boolean }) {
  const cx = room.x + room.width / 2;
  const cy = fy(room.y + room.depth / 2);
  const fs = Math.min(Math.max(Math.min(room.width, room.depth) * 0.18, 0.24), 0.46);
  const maxChars = Math.max(3, Math.floor((room.width - 0.3) / (fs * 0.6)));
  const name = room.name.length > maxChars ? room.name.slice(0, maxChars - 1) + "…" : room.name;
  // Selected room always shows its dimensions; others only when there's space.
  const showDims = selected || Math.min(room.width, room.depth) > 1.8;

  return (
    <g pointerEvents="none" style={{ userSelect: "none" }}>
      <text
        x={cx}
        y={cy - fs * 0.35}
        fontSize={fs}
        fill="#dbe4ee"
        fontWeight={600}
        textAnchor="middle"
      >
        {name}
      </text>
      <text
        x={cx}
        y={cy + fs * 0.85}
        fontSize={fs * 0.78}
        fill="#7c8aa0"
        textAnchor="middle"
        className="font-mono"
      >
        {room.area_m2.toFixed(1)} m²
      </text>
      {showDims && (
        <text
          x={cx}
          y={cy + fs * 1.95}
          fontSize={fs * 0.62}
          fill="#55637a"
          textAnchor="middle"
          className="font-mono"
        >
          {room.width.toFixed(1)} × {room.depth.toFixed(1)}
        </text>
      )}
    </g>
  );
}

// Architectural dimension line with 45° tick marks
function DimLine({
  x1,
  y1,
  x2,
  y2,
  label,
  vertical = false,
}: {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  label: string;
  vertical?: boolean;
}) {
  const tick = 0.14;
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  return (
    <g stroke="#46586f" strokeWidth={0.03} pointerEvents="none">
      <line x1={x1} y1={y1} x2={x2} y2={y2} />
      <line x1={x1 - tick} y1={y1 + tick} x2={x1 + tick} y2={y1 - tick} />
      <line x1={x2 - tick} y1={y2 + tick} x2={x2 + tick} y2={y2 - tick} />
      <text
        x={mx}
        y={my}
        fontSize={0.42}
        fill="#8fa0b8"
        stroke="none"
        textAnchor="middle"
        className="font-mono"
        transform={vertical ? `rotate(-90 ${mx} ${my})` : undefined}
        dy={-0.18}
      >
        {label}
      </text>
    </g>
  );
}

// Everything that does NOT depend on the viewBox. Memoized so pan/zoom
// re-renders (one setVb per pointermove) only touch the <svg> attributes.
const PlanSheet = memo(function PlanSheet({
  rooms,
  bbox,
  activeFloor,
  showMEP,
  conflicts,
  selectedRoomId,
  setSelectedRoom,
  movedRef,
}: {
  rooms: RoomLayout[];
  bbox: BBox;
  activeFloor: number;
  showMEP: boolean;
  conflicts: MEPConflict[];
  selectedRoomId: string | null;
  setSelectedRoom: (id: string | null) => void;
  movedRef: React.MutableRefObject<boolean>;
}) {
  const { t } = useTranslation();
  const { minX, maxX, minY, maxY } = bbox;
  const fy: FlipFn = (y) => minY + maxY - y;
  const floorArea = rooms.reduce((s, r) => s + r.area_m2, 0);
  const scaleSegments = Math.min(5, Math.max(2, Math.round((maxX - minX) / 3)));

  return (
    <g>
      {/* Room fills (clickable) */}
      {rooms.map((r) => {
        const selected = r.room_id === selectedRoomId;
        return (
          <rect
            key={r.room_id}
            x={r.x}
            y={fy(r.y + r.depth)}
            width={r.width}
            height={r.depth}
            fill={selected ? SELECTION_COLOR : ROOM_FILL_2D[r.room_type] || DEFAULT_FILL_2D}
            fillOpacity={selected ? 0.32 : 0.15}
            style={{ cursor: "pointer" }}
            onClick={(e) => {
              e.stopPropagation();
              if (movedRef.current) return;
              setSelectedRoom(selected ? null : r.room_id);
            }}
          />
        );
      })}

      {/* Walls */}
      {rooms.map((r) => (
        <rect
          key={`w-${r.room_id}`}
          x={r.x}
          y={fy(r.y + r.depth)}
          width={r.width}
          height={r.depth}
          fill="none"
          stroke={r.room_id === selectedRoomId ? SELECTION_ACCENT : "#d7e1ec"}
          strokeWidth={WALL_T}
          pointerEvents="none"
        />
      ))}

      {/* Openings */}
      {rooms.map((r) => (
        <g key={`o-${r.room_id}`}>
          {r.doors?.map((d, i) => (
            <DoorSymbol key={`d${i}`} room={r} door={d} fy={fy} />
          ))}
          {r.windows?.map((w, i) => (
            <WindowSymbol key={`win${i}`} room={r} win={w} fy={fy} />
          ))}
        </g>
      ))}

      {/* Labels */}
      {rooms.map((r) => (
        <RoomLabel
          key={`l-${r.room_id}`}
          room={r}
          fy={fy}
          selected={r.room_id === selectedRoomId}
        />
      ))}

      {/* Overall dimensions */}
      <DimLine
        x1={minX}
        y1={minY - 1.4}
        x2={maxX}
        y2={minY - 1.4}
        label={`${(maxX - minX).toFixed(1)} m`}
      />
      <DimLine
        x1={minX - 1.4}
        y1={maxY}
        x2={minX - 1.4}
        y2={minY}
        label={`${(maxY - minY).toFixed(1)} m`}
        vertical
      />
      {/* Extension lines */}
      <g stroke="#2b3a50" strokeWidth={0.02} pointerEvents="none">
        <line x1={minX} y1={minY - 0.2} x2={minX} y2={minY - 1.55} />
        <line x1={maxX} y1={minY - 0.2} x2={maxX} y2={minY - 1.55} />
        <line x1={minX - 0.2} y1={minY} x2={minX - 1.55} y2={minY} />
        <line x1={minX - 0.2} y1={maxY} x2={minX - 1.55} y2={maxY} />
      </g>

      {/* North arrow */}
      <g transform={`translate(${maxX + 1.4} ${minY - 1.2})`} pointerEvents="none">
        <circle r={0.55} fill="none" stroke="#3b4a5f" strokeWidth={0.04} />
        <path
          d="M 0 0.3 L 0 -0.3 M -0.16 -0.1 L 0 -0.34 L 0.16 -0.1"
          fill="none"
          stroke="#8fa0b8"
          strokeWidth={0.06}
          strokeLinecap="round"
        />
        <text y={-0.75} fontSize={0.36} fill="#8fa0b8" textAnchor="middle" fontWeight={700}>
          N
        </text>
      </g>

      {/* Scale bar */}
      <g transform={`translate(${minX} ${maxY + 1.2})`} pointerEvents="none">
        {Array.from({ length: scaleSegments }, (_, i) => (
          <rect
            key={i}
            x={i}
            y={0}
            width={1}
            height={0.16}
            fill={i % 2 === 0 ? "#cbd5e1" : "none"}
            stroke="#cbd5e1"
            strokeWidth={0.025}
          />
        ))}
        {/* A number under every segment boundary */}
        {Array.from({ length: scaleSegments + 1 }, (_, i) => (
          <text
            key={`t${i}`}
            x={i}
            y={0.62}
            fontSize={0.34}
            fill="#55637a"
            textAnchor={i === 0 ? "start" : i === scaleSegments ? "end" : "middle"}
            className="font-mono"
          >
            {i === scaleSegments ? `${i} m` : i}
          </text>
        ))}
      </g>

      {/* Floor caption */}
      <text
        x={maxX}
        y={maxY + 1.7}
        fontSize={0.4}
        fill="#7c8aa0"
        textAnchor="end"
        pointerEvents="none"
      >
        {t("viewer.floor")} {activeFloor} · {floorArea.toFixed(1)} m²
      </text>

      {/* MEP conflict markers */}
      {showMEP &&
        conflicts.map((c) => {
          const color = SEVERITY_COLORS[c.severity] ?? SEVERITY_COLORS.MEDIUM;
          return (
            <g
              key={c.conflict_id}
              transform={`translate(${c.location_x} ${fy(c.location_y)})`}
              pointerEvents="none"
            >
              <circle r={0.16} fill={color} />
              <circle r={0.16} fill="none" stroke={color} strokeWidth={0.05}>
                <animate attributeName="r" values="0.16;0.6" dur="1.6s" repeatCount="indefinite" />
                <animate
                  attributeName="opacity"
                  values="0.8;0"
                  dur="1.6s"
                  repeatCount="indefinite"
                />
              </circle>
            </g>
          );
        })}
    </g>
  );
});

export function PlanView2D() {
  const { t } = useTranslation();
  const result = useStore((s) => s.result);
  const activeFloor = useStore((s) => s.activeFloor);
  const showMEP = useStore((s) => s.showMEP);
  const selectedRoomId = useStore((s) => s.selectedRoomId);
  const setSelectedRoom = useStore((s) => s.setSelectedRoom);

  const svgRef = useRef<SVGSVGElement>(null);
  const [vb, setVb] = useState<VB | null>(null);
  const panRef = useRef<{ sx: number; sy: number; vb: VB; wpp: number } | null>(null);
  const movedRef = useRef(false);

  const rooms = useMemo(() => floorRooms(result, activeFloor), [result, activeFloor]);
  const bbox = useMemo(() => roomsBBox(rooms), [rooms]);

  const fit: VB = useMemo(() => {
    if (!bbox) return { x: -5, y: -5, w: 10, h: 10 };
    return {
      x: bbox.minX - PAD,
      y: bbox.minY - PAD,
      w: bbox.maxX - bbox.minX + PAD * 2,
      h: bbox.maxY - bbox.minY + PAD * 2,
    };
  }, [bbox]);

  // Reset zoom when a new plan arrives or the floor changes
  useEffect(() => {
    setVb(null);
  }, [result?.project_id, activeFloor]);

  // Native wheel listener — must be non-passive to preventDefault page scroll
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const ctm = svg.getScreenCTM();
      if (!ctm) return;
      const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
      const k = e.deltaY > 0 ? 1.12 : 1 / 1.12;
      setVb((prev) => zoomViewBox(prev ?? fit, k, p.x, p.y));
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [fit]);

  if (!result || !bbox) return null;

  const view = vb ?? fit;

  const zoomBy = (k: number) =>
    setVb((prev) => {
      const v = prev ?? fit;
      return zoomViewBox(v, k, v.x + v.w / 2, v.y + v.h / 2);
    });

  const onPointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;
    const svg = svgRef.current;
    const ctm = svg?.getScreenCTM();
    if (!svg || !ctm) return;
    movedRef.current = false;
    panRef.current = { sx: e.clientX, sy: e.clientY, vb: view, wpp: ctm.inverse().a };
    svg.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const p = panRef.current;
    if (!p) return;
    const dx = e.clientX - p.sx;
    const dy = e.clientY - p.sy;
    if (Math.abs(dx) + Math.abs(dy) > 4) movedRef.current = true;
    if (!movedRef.current) return;
    setVb({ x: p.vb.x - dx * p.wpp, y: p.vb.y - dy * p.wpp, w: p.vb.w, h: p.vb.h });
  };

  const onPointerUp = () => {
    panRef.current = null;
  };

  // Grid rects oversized: with preserveAspectRatio="meet" the visible world
  // area can exceed the viewBox in one axis (letterboxing)
  const bgX = view.x - view.w * 2;
  const bgY = view.y - view.h * 2;
  const bgW = view.w * 5;
  const bgH = view.h * 5;

  return (
    <div className="absolute inset-0">
      <svg
        ref={svgRef}
        className="w-full h-full touch-none cursor-grab active:cursor-grabbing"
        style={{ background: BG }}
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        preserveAspectRatio="xMidYMid meet"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
        onDoubleClick={() => setVb(null)}
        onClick={() => {
          if (!movedRef.current) setSelectedRoom(null);
        }}
      >
        <defs>
          <pattern id="grid1m" width={1} height={1} patternUnits="userSpaceOnUse">
            <path d="M 1 0 H 0 V 1" fill="none" stroke="#111a29" strokeWidth={0.02} />
          </pattern>
          <pattern id="grid5m" width={5} height={5} patternUnits="userSpaceOnUse">
            <path d="M 5 0 H 0 V 5" fill="none" stroke="#1a2740" strokeWidth={0.035} />
          </pattern>
        </defs>

        <rect x={bgX} y={bgY} width={bgW} height={bgH} fill="url(#grid1m)" />
        <rect x={bgX} y={bgY} width={bgW} height={bgH} fill="url(#grid5m)" />

        <PlanSheet
          rooms={rooms}
          bbox={bbox}
          activeFloor={activeFloor}
          showMEP={showMEP}
          conflicts={result.mep_conflicts}
          selectedRoomId={selectedRoomId}
          setSelectedRoom={setSelectedRoom}
          movedRef={movedRef}
        />
      </svg>

      {/* Zoom controls; bottom-16 clears the "Show Results" button App puts at bottom-4 right-4 */}
      <div className="absolute right-4 bottom-16 flex flex-col gap-1">
        {[
          { label: "+", action: () => zoomBy(1 / 1.3), title: t("viewer.zoomIn") },
          { label: "−", action: () => zoomBy(1.3), title: t("viewer.zoomOut") },
          { label: "⤢", action: () => setVb(null), title: t("viewer.zoomFit") },
        ].map((b) => (
          <button
            key={b.label}
            onClick={b.action}
            title={b.title}
            className="w-8 h-8 rounded-lg bg-surface-card border border-surface-border text-slate-300 hover:bg-surface-border hover:text-white transition-colors text-sm font-semibold"
          >
            {b.label}
          </button>
        ))}
      </div>
    </div>
  );
}
