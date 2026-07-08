import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useStore } from "../store/useStore";
import { PRESETS, FAMILY_KIDS_MIN, FAMILY_KIDS_MAX, type HouseholdPreset } from "../presets";
import { Chevron, Reveal } from "./disclosure";
import type { RoomType, CountryCode, BuildingShape, Openness, Facing } from "../types";

const PRESET_ICONS: Record<HouseholdPreset, JSX.Element> = {
  couple: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      className="w-full h-full"
    >
      <circle cx="8" cy="7" r="3" />
      <circle cx="16" cy="7" r="3" />
      <path d="M3 21v-1a4 4 0 0 1 4-4h2a4 4 0 0 1 4 4v1M14 16h1a4 4 0 0 1 4 4v1" />
    </svg>
  ),
  family: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      className="w-full h-full"
    >
      <circle cx="7" cy="6" r="2.5" />
      <circle cx="17" cy="6" r="2.5" />
      <circle cx="12" cy="9" r="2" />
      <path d="M3 20v-1a4 4 0 0 1 4-4M21 20v-1a4 4 0 0 0-4-4M9.5 20v-1a2.5 2.5 0 0 1 5 0v1" />
    </svg>
  ),
  single: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      className="w-full h-full"
    >
      <circle cx="12" cy="7" r="3.2" />
      <path d="M6 21v-1a6 6 0 0 1 12 0v1" />
    </svg>
  ),
  rental: (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      className="w-full h-full"
    >
      <path d="M3 11l9-7 9 7M5 10v10h14V10" />
      <circle cx="12" cy="14" r="1.6" />
      <path d="M12 15.6V18" />
    </svg>
  ),
};

const SHAPES: { id: BuildingShape; icon: JSX.Element }[] = [
  {
    id: "rectangular",
    icon: (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinejoin="round"
        className="w-full h-full"
      >
        <rect x="1" y="5" width="22" height="14" />
      </svg>
    ),
  },
  {
    id: "square",
    icon: (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinejoin="round"
        className="w-full h-full"
      >
        <rect x="3" y="3" width="18" height="18" />
      </svg>
    ),
  },
  {
    id: "l_shape",
    icon: (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinejoin="round"
        className="w-full h-full"
      >
        <polygon points="1,1 23,1 23,23 13,23 13,11 1,11" />
      </svg>
    ),
  },
  {
    id: "u_shape",
    icon: (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinejoin="round"
        className="w-full h-full"
      >
        <polygon points="1,1 7,1 7,17 17,17 17,1 23,1 23,23 1,23" />
      </svg>
    ),
  },
  {
    id: "t_shape",
    icon: (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinejoin="round"
        className="w-full h-full"
      >
        <polygon points="1,1 23,1 23,9 15,9 15,23 9,23 9,9 1,9" />
      </svg>
    ),
  },
];

const OPENNESS: Openness[] = ["closed", "mixed", "open"];
const FACINGS: Facing[] = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

const ROOM_TYPES: RoomType[] = [
  "living_room",
  "bedroom",
  "kitchen",
  "bathroom",
  "toilet",
  "hallway",
  "utility",
  "garage",
];

const COUNTRIES: CountryCode[] = ["RU", "KZ", "UA", "BY", "UZ", "DE", "US", "OTHER"];

// Optional positive number: empty/invalid/non-positive input clears the field
// (the backend schema requires gt=0, so 0 is not a meaningful value here).
function parsePositiveFloat(value: string): number | undefined {
  const v = parseFloat(value);
  return Number.isFinite(v) && v > 0 ? v : undefined;
}

// Advanced/secondary inputs fold away behind these so the form leads with the
// few high-value choices (preset + preferences) instead of a wall of fields.
function Collapsible({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-surface-border">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between py-3 group"
      >
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500 group-hover:text-slate-800 transition-colors">
          {title}
        </span>
        <span className="text-slate-400 group-hover:text-slate-600 transition-colors">
          <Chevron open={open} />
        </span>
      </button>
      <Reveal open={open}>
        <div className="pb-3 space-y-4 px-px">{children}</div>
      </Reveal>
    </div>
  );
}

interface Props {
  onGenerate: () => void;
}

export function ParameterForm({ onGenerate }: Props) {
  const { t } = useTranslation();
  const {
    params,
    preset,
    familyKids,
    applyPreset,
    setFamilyKids,
    setGarage,
    setParams,
    addRoom,
    updateRoom,
    removeRoom,
    isGenerating,
  } = useStore();
  const [roomsOpen, setRoomsOpen] = useState(false);
  // "Add room" appends at the END of a possibly-scrolled-out list — without a
  // scroll + flash the new row is invisible and the click looks like a no-op.
  const [justAdded, setJustAdded] = useState<number | null>(null);
  const newRoomRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (justAdded === null) return;
    const scroll = setTimeout(
      () => newRoomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }),
      180
    );
    const clear = setTimeout(() => setJustAdded(null), 1400);
    return () => {
      clearTimeout(scroll);
      clearTimeout(clear);
    };
  }, [justAdded]);
  const hasGarage = params.rooms.some((r) => r.room_type === "garage");

  const totalArea = params.rooms.reduce((s, r) => s + r.area_m2, 0);
  // Rough usable capacity: plot footprint × floors (packing always fits less).
  const plotCapacity =
    params.plot_width_m && params.plot_depth_m
      ? params.plot_width_m * params.plot_depth_m * params.floors
      : null;

  return (
    <div className="flex flex-col gap-5">
      {/* Household preset — the primary entry point. Picking one fills a sane,
          complete room program; manual editing is the advanced path below. */}
      <div>
        <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">
          {t("presets.title")}
        </h2>
        <div className="grid grid-cols-2 gap-2">
          {PRESETS.map((id) => {
            const active = preset === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => applyPreset(id)}
                aria-pressed={active}
                className={`relative flex flex-col gap-1.5 p-2.5 rounded-xl border text-left transition-all duration-150 ${
                  active
                    ? "bg-brand-50 border-brand-500 ring-1 ring-brand-500 shadow-sm"
                    : "bg-surface-card border-surface-border hover:border-slate-300 hover:shadow-sm hover:-translate-y-px"
                }`}
              >
                {active && (
                  <span className="absolute top-1.5 right-1.5 w-4 h-4 rounded-full bg-brand-500 flex items-center justify-center">
                    <svg
                      viewBox="0 0 12 12"
                      fill="none"
                      stroke="#fff"
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="w-2.5 h-2.5"
                    >
                      <path d="M2.5 6.5l2.5 2.5 4.5-5" />
                    </svg>
                  </span>
                )}
                <div
                  className={`w-8 h-8 rounded-lg flex items-center justify-center p-1.5 transition-colors ${
                    active ? "bg-brand-100 text-brand-600" : "bg-surface-panel text-slate-500"
                  }`}
                >
                  {PRESET_ICONS[id]}
                </div>
                <div className="min-w-0">
                  <div
                    className={`text-xs font-semibold ${active ? "text-brand-700" : "text-slate-700"}`}
                  >
                    {t(`presets.${id}`)}
                  </div>
                  <div className="text-[10px] leading-tight text-slate-500 mt-0.5">
                    {t(`presets.${id}Desc`)}
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {preset === "family" && (
          <div className="flex items-center justify-between mt-2.5 px-1">
            <span className="text-xs text-slate-600">{t("presets.kids")}</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setFamilyKids(familyKids - 1)}
                disabled={familyKids <= FAMILY_KIDS_MIN}
                className="w-6 h-6 rounded border border-surface-border text-slate-600 disabled:opacity-40 hover:border-slate-400"
              >
                −
              </button>
              <span className="w-5 text-center text-sm font-semibold text-slate-800">
                {familyKids}
              </span>
              <button
                type="button"
                onClick={() => setFamilyKids(familyKids + 1)}
                disabled={familyKids >= FAMILY_KIDS_MAX}
                className="w-6 h-6 rounded border border-surface-border text-slate-600 disabled:opacity-40 hover:border-slate-400"
              >
                +
              </button>
            </div>
          </div>
        )}

        {/* Garage — a preset modifier like the kid count, valid for every
            household. The engine gives it its own band, so it never squeezes
            the living rooms. The switch reflects the actual program (a hand-
            added garage in custom mode reads as ON). */}
        <div className="flex items-center justify-between mt-2.5 px-1">
          <div className="min-w-0">
            <span className="text-xs text-slate-600">{t("presets.garage")}</span>
            <span className="text-[10px] text-slate-400 ml-1.5">{t("presets.garageHint")}</span>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={hasGarage}
            onClick={() => setGarage(!hasGarage)}
            className={`relative shrink-0 w-9 h-5 rounded-full transition-colors ${
              hasGarage ? "bg-brand-500" : "bg-slate-300"
            }`}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
                hasGarage ? "translate-x-4" : ""
              }`}
            />
          </button>
        </div>
      </div>

      {/* Preferences — the high-value, easy choices stay visible. Shape and site
          details fold into the collapsibles below (progressive disclosure). */}
      <div className="space-y-4">
        {/* Layout openness selector */}
        <div>
          <label className="label mb-1.5">{t("openness.title")}</label>
          <div className="grid grid-cols-3 gap-1.5">
            {OPENNESS.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => setParams({ openness: id })}
                className={`flex flex-col items-center gap-1 py-2 px-1 rounded-lg border transition-all min-w-0 ${
                  params.openness === id
                    ? "bg-brand-50 border-brand-500 text-brand-700"
                    : "bg-surface-card border-surface-border text-slate-500 hover:border-slate-400 hover:text-slate-700"
                }`}
              >
                <span className="w-full text-[11px] font-semibold leading-tight text-center break-words">
                  {t(`openness.${id}`)}
                </span>
                <span className="text-[9px] leading-tight text-slate-500 text-center">
                  {t(`openness.${id}Desc`)}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Budget ↔ spacious — one slider scaling room sizes (and so footprint,
            perimeter and cost) from compact/cheap to spread/pricey. */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="label mb-0">{t("openness.spaciousness")}</label>
            <span className="text-[10px] font-semibold text-brand-700 bg-brand-50 border border-brand-100 rounded-full px-2 py-px transition-colors">
              {t(
                `openness.${
                  params.spaciousness < 0.4
                    ? "sizeCompact"
                    : params.spaciousness > 0.6
                      ? "sizeSpacious"
                      : "sizeBalanced"
                }`
              )}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={params.spaciousness}
            onChange={(e) => setParams({ spaciousness: parseFloat(e.target.value) })}
            className="range-brand w-full"
            style={{ backgroundSize: `${params.spaciousness * 100}% 100%` }}
          />
          <div className="flex justify-between text-[10px] text-slate-500 mt-1">
            <span>{t("openness.budget")}</span>
            <span>{t("openness.spacious")}</span>
          </div>
        </div>
      </div>

      {/* Shape & orientation — advanced, collapsed by default */}
      <Collapsible title={t("form.sectionShapeOrient")}>
        <div>
          <label className="label mb-1.5">{t("form.houseShape")}</label>
          <div className="grid grid-cols-5 gap-1.5">
            {SHAPES.map((shape) => (
              <button
                key={shape.id}
                type="button"
                onClick={() => setParams({ building_shape: shape.id })}
                className={`flex flex-col items-center gap-1 py-2 px-1 rounded-lg border transition-all ${
                  params.building_shape === shape.id
                    ? "bg-brand-50 border-brand-500 text-brand-700"
                    : "bg-surface-card border-surface-border text-slate-500 hover:border-slate-400 hover:text-slate-700"
                }`}
                title={t(`shapes.${shape.id}`)}
              >
                <div className="w-7 h-7">{shape.icon}</div>
                <span className="text-[9px] leading-tight text-center">
                  {t(`shapes.${shape.id}`)}
                </span>
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="label">{t("daylight.facing")}</label>
          <select
            className="input"
            value={params.facing}
            onChange={(e) => setParams({ facing: e.target.value as Facing })}
          >
            {FACINGS.map((d) => (
              <option key={d} value={d}>
                {t(`daylight.${d}`)}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 mt-2 cursor-pointer text-xs text-slate-600">
            <input
              type="checkbox"
              checked={params.auto_orient}
              onChange={(e) => setParams({ auto_orient: e.target.checked })}
              className="accent-brand-500"
            />
            {t("daylight.autoOrient")}
          </label>
        </div>
      </Collapsible>

      {/* Country, floors, region & plot — advanced, collapsed by default */}
      <Collapsible title={t("form.sectionSite")}>
        <div className="flex gap-3">
          <div className="flex-1">
            <label className="label">{t("form.country")}</label>
            <select
              className="input"
              value={params.country}
              onChange={(e) => setParams({ country: e.target.value as CountryCode })}
            >
              {COUNTRIES.map((c) => (
                <option key={c} value={c}>
                  {t(`countries.${c}`)}
                </option>
              ))}
            </select>
          </div>
          <div className="w-24">
            <label className="label">{t("form.floors")}</label>
            <input
              type="number"
              min={1}
              max={5}
              className="input"
              value={params.floors}
              onChange={(e) => setParams({ floors: parseInt(e.target.value) || 1 })}
            />
          </div>
        </div>

        <div>
          <label className="label">{t("form.region")}</label>
          <input
            type="text"
            className="input"
            placeholder={t("form.regionPh")}
            value={params.region || ""}
            onChange={(e) => setParams({ region: e.target.value || undefined })}
          />
        </div>

        <div>
          <label className="label">{t("form.plotSize")}</label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              min={5}
              max={200}
              step={0.5}
              className="input"
              placeholder={t("form.plotWidth")}
              value={params.plot_width_m ?? ""}
              onChange={(e) => setParams({ plot_width_m: parsePositiveFloat(e.target.value) })}
            />
            <span className="text-slate-600 text-sm">×</span>
            <input
              type="number"
              min={5}
              max={200}
              step={0.5}
              className="input"
              placeholder={t("form.plotDepth")}
              value={params.plot_depth_m ?? ""}
              onChange={(e) => setParams({ plot_depth_m: parsePositiveFloat(e.target.value) })}
            />
          </div>
          {plotCapacity !== null && totalArea > plotCapacity && (
            <p className="text-xs text-amber-600 mt-1.5 leading-snug">
              {t("form.plotWarning", {
                total: totalArea.toFixed(0),
                capacity: plotCapacity.toFixed(0),
                floors: params.floors,
              })}
            </p>
          )}
        </div>
      </Collapsible>

      {/* Rooms — collapsed summary by default; the program comes from the
          preset, so the detailed editor is the advanced path. */}
      <div>
        <button
          type="button"
          onClick={() => setRoomsOpen((v) => !v)}
          className="w-full flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5 mb-2 text-left"
        >
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">
            {t("form.rooms")}
            <span className="ml-2 text-brand-500 font-mono normal-case text-xs whitespace-nowrap">
              {t("presets.roomsSummary", {
                count: params.rooms.length,
                area: totalArea.toFixed(0),
              })}
            </span>
          </h2>
          <span className="text-xs text-brand-600 hover:text-brand-700 transition-colors flex-shrink-0 inline-flex items-center gap-1 whitespace-nowrap">
            {roomsOpen ? t("presets.hide") : t("presets.editManually")}
            <Chevron open={roomsOpen} />
          </span>
        </button>

        <Reveal open={roomsOpen}>
          <div className="px-px">
            <div className="flex justify-end mb-2">
              <button
                onClick={() => {
                  addRoom({ room_type: "bedroom", area_m2: 12 });
                  setRoomsOpen(true);
                  setJustAdded(params.rooms.length);
                }}
                className="text-xs text-brand-600 hover:text-brand-700 transition-colors"
              >
                {t("form.addRoom")}
              </button>
            </div>
            <div className="flex flex-col gap-2">
              {params.rooms.map((room, idx) => (
                <div
                  key={idx}
                  ref={idx === justAdded ? newRoomRef : undefined}
                  className={`card p-3 flex flex-col gap-2 ${idx === justAdded ? "flash-new" : ""}`}
                >
                  <div className="flex items-center gap-2">
                    <select
                      className="input text-sm flex-1"
                      value={room.room_type}
                      onChange={(e) => updateRoom(idx, { room_type: e.target.value as RoomType })}
                    >
                      {ROOM_TYPES.map((rt) => (
                        <option key={rt} value={rt}>
                          {t(`roomTypes.${rt}`)}
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={() => removeRoom(idx)}
                      className="text-slate-600 hover:text-red-400 transition-colors text-lg leading-none"
                      title={t("form.removeRoom")}
                    >
                      ×
                    </button>
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min={1}
                      max={200}
                      step={0.5}
                      className="input text-sm"
                      value={room.area_m2}
                      onChange={(e) =>
                        updateRoom(idx, { area_m2: parseFloat(e.target.value) || 1 })
                      }
                    />
                    <span className="text-xs text-slate-500 whitespace-nowrap">m²</span>
                  </div>
                  <input
                    type="text"
                    className="input text-sm"
                    placeholder={t("form.customName")}
                    value={room.name || ""}
                    onChange={(e) => updateRoom(idx, { name: e.target.value || undefined })}
                  />
                </div>
              ))}
            </div>
          </div>
        </Reveal>
      </div>

      <div
        style={{
          position: "sticky",
          bottom: 0,
          background: "linear-gradient(to bottom, transparent, var(--surface-panel) 25%)",
          paddingTop: 16,
          paddingBottom: 16,
          marginTop: 4,
        }}
      >
        <button
          onClick={onGenerate}
          disabled={isGenerating || params.rooms.length === 0}
          className="btn-primary w-full py-3 text-base"
        >
          {isGenerating ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              {t("form.generatingBtn")}
            </span>
          ) : (
            t("form.generate")
          )}
        </button>
      </div>
    </div>
  );
}
