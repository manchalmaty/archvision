import { useStore } from "../store/useStore";
import type { RoomType, CountryCode, BuildingShape } from "../types";

const SHAPES: { id: BuildingShape; label: string; icon: JSX.Element }[] = [
  {
    id: "rectangular",
    label: "Прямоуг.",
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
    label: "Квадрат.",
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
    label: "Г-образн.",
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
    label: "П-образн.",
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
    label: "Т-образн.",
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

const ROOM_TYPES: { value: RoomType; label: string }[] = [
  { value: "living_room", label: "Living Room" },
  { value: "bedroom", label: "Bedroom" },
  { value: "kitchen", label: "Kitchen" },
  { value: "bathroom", label: "Bathroom" },
  { value: "toilet", label: "Toilet" },
  { value: "hallway", label: "Hallway" },
  { value: "utility", label: "Utility Room" },
  { value: "garage", label: "Garage" },
];

const COUNTRIES: { value: CountryCode; label: string }[] = [
  { value: "RU", label: "Russia" },
  { value: "KZ", label: "Kazakhstan" },
  { value: "UA", label: "Ukraine" },
  { value: "BY", label: "Belarus" },
  { value: "UZ", label: "Uzbekistan" },
  { value: "DE", label: "Germany" },
  { value: "US", label: "USA" },
  { value: "OTHER", label: "Other" },
];

interface Props {
  onGenerate: () => void;
}

export function ParameterForm({ onGenerate }: Props) {
  const { params, setParams, addRoom, updateRoom, removeRoom, isGenerating } = useStore();

  const totalArea = params.rooms.reduce((s, r) => s + r.area_m2, 0);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
          Building Parameters
        </h2>

        {/* House shape selector */}
        <div className="mb-4">
          <label className="label mb-1.5">Форма дома</label>
          <div className="grid grid-cols-5 gap-1.5">
            {SHAPES.map((shape) => (
              <button
                key={shape.id}
                type="button"
                onClick={() => setParams({ building_shape: shape.id })}
                className={`flex flex-col items-center gap-1 py-2 px-1 rounded-lg border transition-all ${
                  params.building_shape === shape.id
                    ? "bg-brand-600/25 border-brand-500 text-brand-400"
                    : "bg-surface-card border-surface-border text-slate-500 hover:border-slate-500 hover:text-slate-300"
                }`}
                title={shape.label}
              >
                <div className="w-7 h-7">{shape.icon}</div>
                <span className="text-[9px] leading-tight text-center">{shape.label}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="flex gap-3 mb-3">
          <div className="flex-1">
            <label className="label">Country</label>
            <select
              className="input"
              value={params.country}
              onChange={(e) => setParams({ country: e.target.value as CountryCode })}
            >
              {COUNTRIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>
          <div className="w-24">
            <label className="label">Floors</label>
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
          <label className="label">Region (optional)</label>
          <input
            type="text"
            className="input"
            placeholder="e.g. Алматы, Moscow, California"
            value={params.region || ""}
            onChange={(e) => setParams({ region: e.target.value || undefined })}
          />
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
            Rooms
            <span className="ml-2 text-brand-500 font-mono normal-case text-xs">
              {totalArea.toFixed(0)} m²
            </span>
          </h2>
          <button
            onClick={() => addRoom({ room_type: "bedroom", area_m2: 12 })}
            className="text-xs text-brand-500 hover:text-brand-400 transition-colors"
          >
            + Add Room
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
                    <option key={rt.value} value={rt.value}>
                      {rt.label}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => removeRoom(idx)}
                  className="text-slate-600 hover:text-red-400 transition-colors text-lg leading-none"
                  title="Remove room"
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
                placeholder="Custom name (optional)"
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
          background: "linear-gradient(to bottom, transparent, #0b0e16 30%)",
          paddingTop: 16,
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
              Generating…
            </span>
          ) : (
            "Generate Plan"
          )}
        </button>
        <p className="text-xs text-slate-600 text-center mt-2 pb-2">
          IFC · 3D model · MEP routing · cost estimate
        </p>
      </div>
    </div>
  );
}
