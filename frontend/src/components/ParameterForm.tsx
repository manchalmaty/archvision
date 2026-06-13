import { useTranslation } from "react-i18next";
import { useStore } from "../store/useStore";
import type { RoomType, CountryCode, BuildingShape } from "../types";

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

interface Props {
  onGenerate: () => void;
}

export function ParameterForm({ onGenerate }: Props) {
  const { t } = useTranslation();
  const { params, setParams, addRoom, updateRoom, removeRoom, isGenerating } = useStore();

  const totalArea = params.rooms.reduce((s, r) => s + r.area_m2, 0);
  // Rough usable capacity: plot footprint × floors (packing always fits less).
  const plotCapacity =
    params.plot_width_m && params.plot_depth_m
      ? params.plot_width_m * params.plot_depth_m * params.floors
      : null;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">
          {t("form.buildingParams")}
        </h2>

        {/* House shape selector */}
        <div className="mb-4">
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

        <div className="flex gap-3 mb-3">
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

        {/* Plot dimensions — optional; constrains the building footprint */}
        <div className="mt-3">
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
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">
            {t("form.rooms")}
            <span className="ml-2 text-brand-500 font-mono normal-case text-xs">
              {totalArea.toFixed(0)} m²
            </span>
          </h2>
          <button
            onClick={() => addRoom({ room_type: "bedroom", area_m2: 12 })}
            className="text-xs text-brand-600 hover:text-brand-700 transition-colors"
          >
            {t("form.addRoom")}
          </button>
        </div>

        <div className="flex flex-col gap-2">
          {params.rooms.map((room, idx) => (
            <div key={idx} className="card p-3 flex flex-col gap-2">
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
                  onChange={(e) => updateRoom(idx, { area_m2: parseFloat(e.target.value) || 1 })}
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

      <div
        style={{
          position: "sticky",
          bottom: 0,
          background: "linear-gradient(to bottom, transparent, #f1f5f9 25%)",
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
        <p className="text-xs text-slate-600 text-center mt-2 pb-2">{t("form.formFooter")}</p>
      </div>
    </div>
  );
}
