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
import { roomDisplayName } from "./roomName";
import type { RoomLayout, MEPConflict, DoorSpec, WindowSpec } from "../types";

const WALL_T = 0.18; // wall line thickness in plan units (m)
const PAD = 2.8; // sheet margin around the plan for dimension lines (m)
const BG = "#ffffff";

// Daylight rating colors (amber = good sun, slate = ok, grey = poor). Drawn as a
// rayed SUN glyph — NOT a plain dot — so it can't be mistaken for an MEP-conflict
// marker (which is a plain coloured circle).
const SUN_FILL: Record<string, string> = { good: "#f59e0b", ok: "#94a3b8", poor: "#cbd5e1" };
const SUN_RAYS = Array.from({ length: 8 }, (_, i) => {
  const a = (i * Math.PI) / 4;
  return [Math.cos(a), Math.sin(a)] as const;
});

// MEP draft layer (plumbing): wet points + a shared riser + approximate branch
// lines. Cyan keeps it distinct from windows (blue) and conflicts (red/amber).
const MEP_COLOR = "#0891b2";
const WET_TYPES: ReadonlySet<string> = new Set(["kitchen", "bathroom", "toilet", "utility"]);

// Mirror of backend riser_xy(): centre of the largest wet room on the lowest wet floor.
function computeRiser(rooms: RoomLayout[]): { x: number; y: number } | null {
  const wet = rooms.filter((r) => WET_TYPES.has(r.room_type));
  if (!wet.length) return null;
  const low = Math.min(...wet.map((r) => r.floor));
  const anchor = wet
    .filter((r) => r.floor === low)
    .reduce((a, b) => (a.width * a.depth >= b.width * b.depth ? a : b));
  return { x: anchor.x + anchor.width / 2, y: anchor.y + anchor.depth / 2 };
}

function WaterDrop({ cx, cy }: { cx: number; cy: number }) {
  // White halo disc lifts the drop off coloured room fills; the drop itself is
  // slightly larger with a white keyline so it stays crisp when zoomed out.
  return (
    <g>
      <circle cx={cx} cy={cy} r={0.3} fill="#ffffff" opacity={0.85} />
      <path
        d={`M ${cx} ${cy - 0.26} L ${cx + 0.14} ${cy + 0.04} L ${cx - 0.14} ${cy + 0.04} Z`}
        fill={MEP_COLOR}
        stroke="#ffffff"
        strokeWidth={0.03}
      />
      <circle
        cx={cx}
        cy={cy + 0.06}
        r={0.16}
        fill={MEP_COLOR}
        stroke="#ffffff"
        strokeWidth={0.04}
      />
    </g>
  );
}

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
  const opening = door.kind === "opening"; // wide cased gap, no swing leaf
  const j = WALL_T / 2 + 0.03; // jamb tick half-length
  let gap: { x1: number; y1: number; x2: number; y2: number };
  let leaf: { x1: number; y1: number; x2: number; y2: number };
  let arc: string;
  let jambs: { x1: number; y1: number; x2: number; y2: number }[];

  if (door.wall === "S" || door.wall === "N") {
    const x1 = room.x + clampPos(door.position, dw, room.width);
    const x2 = x1 + dw;
    const yw = door.wall === "S" ? fy(room.y) : fy(room.y + room.depth);
    const dir = door.wall === "S" ? -1 : 1; // into the room, in SVG y
    const sweep = door.wall === "S" ? 0 : 1;
    gap = { x1, y1: yw, x2, y2: yw };
    leaf = { x1, y1: yw, x2: x1, y2: yw + dir * dw };
    arc = `M ${x2} ${yw} A ${dw} ${dw} 0 0 ${sweep} ${x1} ${yw + dir * dw}`;
    jambs = [
      { x1, y1: yw - j, x2: x1, y2: yw + j },
      { x1: x2, y1: yw - j, x2, y2: yw + j },
    ];
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
    jambs = [
      { x1: xw - j, y1: yTop, x2: xw + j, y2: yTop },
      { x1: xw - j, y1: yBot, x2: xw + j, y2: yBot },
    ];
  }

  // An opening just erases the wall across its width and frames the two jambs —
  // no swing arc or leaf — so the rooms read as one continuous volume.
  return (
    <g pointerEvents="none">
      <line {...gap} stroke={BG} strokeWidth={WALL_T + 0.08} />
      {opening ? (
        jambs.map((jb, i) => (
          <line key={i} {...jb} stroke="#1f2937" strokeWidth={0.05} strokeLinecap="round" />
        ))
      ) : (
        <>
          <path d={arc} fill="none" stroke="#64748b" strokeWidth={0.03} />
          <line {...leaf} stroke="#d9a05b" strokeWidth={0.07} strokeLinecap="round" />
        </>
      )}
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
      <rect x={x} y={y} width={w} height={h} fill="#e0f2fe" stroke="#0ea5e9" strokeWidth={0.035} />
      <line {...mid} stroke="#7dd3fc" strokeWidth={0.025} />
    </g>
  );
}

function RoomLabel({
  room,
  label,
  fy,
  selected,
}: {
  room: RoomLayout;
  label: string;
  fy: FlipFn;
  selected: boolean;
}) {
  const { t } = useTranslation();
  const cx = room.x + room.width / 2;
  const cy = fy(room.y + room.depth / 2);
  const fs = Math.min(Math.max(Math.min(room.width, room.depth) * 0.18, 0.24), 0.46);
  const maxChars = Math.max(3, Math.floor((room.width - 0.3) / (fs * 0.6)));
  const name = label.length > maxChars ? label.slice(0, maxChars - 1) + "…" : label;
  // Keep on-plan labels to name + area; dimensions show only for the selected
  // room (deliberate) — otherwise the hover card carries them, so the third line
  // no longer stacks onto walls/dimension lines.
  const showDims = selected;

  return (
    <g pointerEvents="none" style={{ userSelect: "none" }}>
      {room.sun &&
        (() => {
          const sx = room.x + 0.45;
          const sy = fy(room.y + room.depth) + 0.45;
          const c = SUN_FILL[room.sun];
          return (
            <g>
              <title>{t(`daylight.${room.sun}`)}</title>
              <circle cx={sx} cy={sy} r={0.36} fill="#ffffff" opacity={0.85} />
              {SUN_RAYS.map(([dx, dy], i) => (
                <line
                  key={i}
                  x1={sx + dx * 0.2}
                  y1={sy + dy * 0.2}
                  x2={sx + dx * 0.31}
                  y2={sy + dy * 0.31}
                  stroke={c}
                  strokeWidth={0.06}
                  strokeLinecap="round"
                />
              ))}
              <circle cx={sx} cy={sy} r={0.15} fill={c} stroke="#ffffff" strokeWidth={0.04} />
            </g>
          );
        })()}
      <text
        x={cx}
        y={cy - fs * 0.35}
        fontSize={fs}
        fill="#1f2937"
        fontWeight={600}
        textAnchor="middle"
      >
        {name}
      </text>
      <text
        x={cx}
        y={cy + fs * 0.85}
        fontSize={fs * 0.78}
        fill="#6b7280"
        textAnchor="middle"
        className="font-mono"
      >
        {(room.width * room.depth).toFixed(1)} m²
      </text>
      {showDims && (
        <text
          x={cx}
          y={cy + fs * 1.95}
          fontSize={fs * 0.62}
          fill="#9ca3af"
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
    <g stroke="#9ca3af" strokeWidth={0.03} pointerEvents="none">
      <line x1={x1} y1={y1} x2={x2} y2={y2} />
      <line x1={x1 - tick} y1={y1 + tick} x2={x1 + tick} y2={y1 - tick} />
      <line x1={x2 - tick} y1={y2 + tick} x2={x2 + tick} y2={y2 - tick} />
      <text
        x={mx}
        y={my}
        fontSize={0.42}
        fill="#6b7280"
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

// Hovered plan object (room or conflict dot) + screen position, for the
// Finch-style floating metrics card.
type HoverInfo = { x: number; y: number; room?: RoomLayout; conflict?: MEPConflict };

// Everything that does NOT depend on the viewBox. Memoized so pan/zoom
// re-renders (one setVb per pointermove) only touch the <svg> attributes.
const PlanSheet = memo(function PlanSheet({
  rooms,
  bbox,
  activeFloor,
  showMEP,
  conflicts,
  riser,
  selectedRoomId,
  setSelectedRoom,
  movedRef,
  onHover,
}: {
  rooms: RoomLayout[];
  bbox: BBox;
  activeFloor: number;
  showMEP: boolean;
  conflicts: MEPConflict[];
  riser: { x: number; y: number } | null;
  selectedRoomId: string | null;
  setSelectedRoom: (id: string | null) => void;
  movedRef: React.MutableRefObject<boolean>;
  onHover: (h: HoverInfo | null) => void;
}) {
  const { t } = useTranslation();
  const { minX, maxX, minY, maxY } = bbox;
  const fy: FlipFn = (y) => minY + maxY - y;
  const floorArea = rooms.reduce((s, r) => s + r.width * r.depth, 0);
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
            onMouseMove={(e) => onHover({ room: r, x: e.clientX, y: e.clientY })}
            onMouseLeave={() => onHover(null)}
          />
        );
      })}

      {/* Walls — solid "poché" band (filled ring between outer and inner
          rectangle) so walls read as real walls, not a thin outline. Adjacent
          rooms overlap their bands on shared walls; acceptable at sketch level. */}
      {rooms.map((r) => {
        const x = r.x;
        const yT = fy(r.y + r.depth);
        const w = r.width;
        const d = r.depth;
        const t = WALL_T;
        const o = t / 2; // band centred on the room boundary
        // Outer + inner rectangles (same winding) → evenodd fills only the wall
        // band. Centring on the boundary makes adjacent rooms' bands coincide
        // (one clean shared wall) and lets door/window gap-erases cover it.
        const ring =
          `M ${x - o} ${yT - o} h ${w + t} v ${d + t} h ${-(w + t)} Z ` +
          `M ${x + o} ${yT + o} h ${w - t} v ${d - t} h ${-(w - t)} Z`;
        return (
          <path
            key={`w-${r.room_id}`}
            d={ring}
            fillRule="evenodd"
            fill={r.room_id === selectedRoomId ? SELECTION_ACCENT : "#1f2937"}
            pointerEvents="none"
          />
        );
      })}

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
          label={roomDisplayName(r, t)}
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
      <g stroke="#cbd5e1" strokeWidth={0.02} pointerEvents="none">
        <line x1={minX} y1={minY - 0.2} x2={minX} y2={minY - 1.55} />
        <line x1={maxX} y1={minY - 0.2} x2={maxX} y2={minY - 1.55} />
        <line x1={minX - 0.2} y1={minY} x2={minX - 1.55} y2={minY} />
        <line x1={minX - 0.2} y1={maxY} x2={minX - 1.55} y2={maxY} />
      </g>

      {/* North arrow */}
      <g transform={`translate(${maxX + 1.4} ${minY - 1.2})`} pointerEvents="none">
        <circle r={0.55} fill="none" stroke="#cbd5e1" strokeWidth={0.04} />
        <path
          d="M 0 0.3 L 0 -0.3 M -0.16 -0.1 L 0 -0.34 L 0.16 -0.1"
          fill="none"
          stroke="#6b7280"
          strokeWidth={0.06}
          strokeLinecap="round"
        />
        <text y={-0.75} fontSize={0.36} fill="#6b7280" textAnchor="middle" fontWeight={700}>
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
            fill={i % 2 === 0 ? "#94a3b8" : "none"}
            stroke="#94a3b8"
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
            fill="#9ca3af"
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
        fill="#6b7280"
        textAnchor="end"
        pointerEvents="none"
      >
        {t("viewer.floor")} {activeFloor} · {floorArea.toFixed(1)} m²
      </text>

      {/* MEP draft layer — wet points + shared riser + approximate branch lines.
          Everything runs along the TOP of the wet band (just inside the back
          wall) so it never overlaps the centred room labels. */}
      {showMEP &&
        riser &&
        (() => {
          const wet = rooms.filter((r) => WET_TYPES.has(r.room_type));
          if (!wet.length) return null;
          const dropOf = (r: RoomLayout) => ({ x: r.x + r.width / 2, y: fy(r.y + r.depth) + 0.45 });
          const bandTop = Math.max(...wet.map((r) => r.y + r.depth)); // back wall (max y)
          const rx = riser.x;
          const ry = fy(bandTop) + 0.45;
          return (
            <g pointerEvents="none">
              {wet.map((r) => {
                const d = dropOf(r);
                return (
                  <line
                    key={`mep-b-${r.room_id}`}
                    x1={d.x}
                    y1={d.y}
                    x2={rx}
                    y2={ry}
                    stroke={MEP_COLOR}
                    strokeWidth={0.06}
                    strokeDasharray="0.26 0.16"
                  />
                );
              })}
              {wet.map((r) => {
                const d = dropOf(r);
                return <WaterDrop key={`mep-d-${r.room_id}`} cx={d.x} cy={d.y} />;
              })}
              {/* Riser: stacked-ring glyph at the shared stack location */}
              <g transform={`translate(${rx} ${ry})`}>
                <circle r={0.26} fill="#ffffff" stroke={MEP_COLOR} strokeWidth={0.06} />
                <circle r={0.14} fill="none" stroke={MEP_COLOR} strokeWidth={0.045} />
                <circle r={0.05} fill={MEP_COLOR} />
              </g>
            </g>
          );
        })()}

      {/* MEP conflict markers — the solid dot is hoverable (with a padded hit
          area) and raises the floating card with the localized fix hint. */}
      {showMEP &&
        conflicts.map((c) => {
          const color = SEVERITY_COLORS[c.severity] ?? SEVERITY_COLORS.MEDIUM;
          return (
            <g key={c.conflict_id} transform={`translate(${c.location_x} ${fy(c.location_y)})`}>
              <circle
                r={0.16}
                fill={color}
                stroke="#ffffff"
                strokeWidth={0.04}
                pointerEvents="none"
              />
              <circle r={0.16} fill="none" stroke={color} strokeWidth={0.05} pointerEvents="none">
                <animate attributeName="r" values="0.16;0.6" dur="1.6s" repeatCount="indefinite" />
                <animate
                  attributeName="opacity"
                  values="0.8;0"
                  dur="1.6s"
                  repeatCount="indefinite"
                />
              </circle>
              <circle
                r={0.34}
                fill="transparent"
                style={{ cursor: "help" }}
                onMouseMove={(e) => onHover({ conflict: c, x: e.clientX, y: e.clientY })}
                onMouseLeave={() => onHover(null)}
              />
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
  const rightPanelOpen = useStore((s) => s.rightPanelOpen);
  const setSelectedRoom = useStore((s) => s.setSelectedRoom);

  const svgRef = useRef<SVGSVGElement>(null);
  const [vb, setVb] = useState<VB | null>(null);
  const panRef = useRef<{ sx: number; sy: number; vb: VB; wpp: number } | null>(null);
  const movedRef = useRef(false);
  const [hover, setHover] = useState<HoverInfo | null>(null);

  const rooms = useMemo(() => floorRooms(result, activeFloor), [result, activeFloor]);
  const bbox = useMemo(() => roomsBBox(rooms), [rooms]);
  // Riser is anchored on the lowest wet floor, so derive it from ALL rooms.
  const riser = useMemo(() => (result ? computeRiser(result.rooms) : null), [result]);

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
            <path d="M 1 0 H 0 V 1" fill="none" stroke="#eef2f6" strokeWidth={0.02} />
          </pattern>
          <pattern id="grid5m" width={5} height={5} patternUnits="userSpaceOnUse">
            <path
              d="M 5 0 H 0 V 5"
              fill="none"
              style={{ stroke: "var(--surface-border)" }}
              strokeWidth={0.035}
            />
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
          riser={riser}
          selectedRoomId={selectedRoomId}
          setSelectedRoom={setSelectedRoom}
          movedRef={movedRef}
          onHover={setHover}
        />
      </svg>

      {/* Finch-style floating metrics card — appears on hover (room metrics or
          conflict explanation), so numbers don't all hang on the plan at once
          and labels can stay minimal. */}
      {hover && !panRef.current && (
        <div
          className="hover-card"
          style={{
            position: "fixed",
            left: Math.min(hover.x + 16, window.innerWidth - (hover.conflict ? 256 : 210)),
            top: Math.min(hover.y + 16, window.innerHeight - 120),
            pointerEvents: "none",
            zIndex: 50,
            width: hover.conflict ? 236 : 190,
            padding: "9px 11px",
            fontFamily: "Inter, system-ui, sans-serif",
          }}
        >
          {hover.room && (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 5 }}>
                <span
                  style={{
                    width: 9,
                    height: 9,
                    borderRadius: 3,
                    background: ROOM_FILL_2D[hover.room.room_type] || DEFAULT_FILL_2D,
                    flexShrink: 0,
                  }}
                />
                <span style={{ fontSize: 13, fontWeight: 600, color: "#161616" }}>
                  {roomDisplayName(hover.room, t)}
                </span>
              </div>
              <div style={{ fontSize: 12, color: "#475569", fontFamily: "monospace" }}>
                {(hover.room.width * hover.room.depth).toFixed(1)} m²
                <span style={{ color: "#cbd5e1" }}> · </span>
                {hover.room.width.toFixed(1)} × {hover.room.depth.toFixed(1)} m
              </div>
              {hover.room.sun && (
                <div
                  style={{
                    fontSize: 11,
                    marginTop: 5,
                    display: "flex",
                    alignItems: "center",
                    gap: 5,
                    color: hover.room.sun === "good" ? "#b45309" : "#64748b",
                  }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      background: SUN_FILL[hover.room.sun],
                      display: "inline-block",
                    }}
                  />
                  {t(`daylight.${hover.room.sun}`)}
                </div>
              )}
            </>
          )}
          {hover.conflict && (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
                <span
                  style={{
                    width: 9,
                    height: 9,
                    borderRadius: "50%",
                    background: SEVERITY_COLORS[hover.conflict.severity] ?? SEVERITY_COLORS.MEDIUM,
                    flexShrink: 0,
                  }}
                />
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    letterSpacing: "0.05em",
                    color: "#334155",
                  }}
                >
                  {hover.conflict.severity}
                </span>
              </div>
              <div style={{ fontSize: 12, color: "#334155", lineHeight: 1.45 }}>
                {hover.conflict.description}
              </div>
              <div style={{ fontSize: 11, color: "#64748b", marginTop: 5, lineHeight: 1.45 }}>
                {t(`mepHints.${hover.conflict.conflict_type}`, {
                  defaultValue: t("mepHints.default"),
                })}
              </div>
            </>
          )}
        </div>
      )}

      {/* Plan zoom — grouped widget with a live % readout so it reads
          unmistakably as a viewer zoom (the bare +/− was ambiguous: "scale of
          what?"). Clicking the % fits the plan back to 100%. bottom-20 clears
          the "Show Results" button App puts at bottom-4. */}
      <div
        className="absolute bottom-20 z-20 flex flex-col items-stretch w-9 rounded-xl overflow-hidden border border-surface-border bg-surface-card shadow-sm transition-[right] duration-200"
        style={{ right: rightPanelOpen ? 336 : 16 }}
      >
        <button
          onClick={() => zoomBy(1 / 1.3)}
          title={t("viewer.zoomIn")}
          className="h-8 text-slate-600 hover:bg-surface-border hover:text-slate-900 transition-colors text-base font-semibold"
        >
          +
        </button>
        <button
          onClick={() => setVb(null)}
          title={t("viewer.zoomFit")}
          className="py-1 text-center text-[10px] font-mono text-slate-500 hover:text-brand-600 border-y border-surface-border transition-colors"
        >
          {Math.round((fit.w / view.w) * 100)}%
        </button>
        <button
          onClick={() => zoomBy(1.3)}
          title={t("viewer.zoomOut")}
          className="h-8 text-slate-600 hover:bg-surface-border hover:text-slate-900 transition-colors text-base font-semibold"
        >
          −
        </button>
      </div>
    </div>
  );
}
