import { create } from "zustand";
import type { BuildingParams, GenerationResult, RoomInput } from "../types";
import { buildPresetRooms, FAMILY_KIDS_DEFAULT, type HouseholdPreset } from "../presets";

const STORAGE_KEY = "archvision_params_v1";
const PRESET_KEY = "archvision_preset_v1";

/** "custom" = the room list has been hand-edited away from any preset program. */
export type ActivePreset = HouseholdPreset | "custom";

function loadPreset(): { preset: ActivePreset; familyKids: number } {
  try {
    const raw = localStorage.getItem(PRESET_KEY);
    if (raw) return { preset: "couple", familyKids: FAMILY_KIDS_DEFAULT, ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return { preset: "couple", familyKids: FAMILY_KIDS_DEFAULT };
}

function savePreset(preset: ActivePreset, familyKids: number) {
  try {
    localStorage.setItem(PRESET_KEY, JSON.stringify({ preset, familyKids }));
  } catch {
    /* storage unavailable — non-fatal */
  }
}

// The active preset is only "real" while the room program still equals what that
// preset would build. Hand-edits drift the program, so rather than persist
// "custom" on every keystroke (which would hammer localStorage), we re-derive it
// on load by comparing the stored rooms against the stored preset's program.
// DEFAULT_PARAMS equals the `couple` program, so a fresh load resolves to couple.
export function deriveActivePreset(
  rooms: RoomInput[],
  stored: { preset: ActivePreset; familyKids: number }
): { preset: ActivePreset; familyKids: number } {
  if (stored.preset === "custom") return stored;
  const program = buildPresetRooms(stored.preset, stored.familyKids);
  const matches =
    rooms.length === program.length &&
    program.every(
      (p, i) =>
        rooms[i].room_type === p.room_type && rooms[i].area_m2 === p.area_m2 && !rooms[i].name
    );
  return matches ? stored : { preset: "custom", familyKids: stored.familyKids };
}

const DEFAULT_PARAMS: BuildingParams = {
  rooms: [
    { room_type: "living_room", area_m2: 20 },
    { room_type: "bedroom", area_m2: 14 },
    { room_type: "kitchen", area_m2: 10 },
    { room_type: "bathroom", area_m2: 5 },
    { room_type: "toilet", area_m2: 2 },
    { room_type: "hallway", area_m2: 6 },
  ],
  country: "RU",
  floors: 1,
  building_shape: "rectangular",
  openness: "closed",
  spaciousness: 0.5,
  facing: "N",
  auto_orient: false,
};

function loadParams(): BuildingParams {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...DEFAULT_PARAMS, ...JSON.parse(raw) };
  } catch {
    /* corrupt or unavailable storage — fall back to defaults */
  }
  return DEFAULT_PARAMS;
}

// Debounced: mutators fire on every keystroke; persisting once after the
// user pauses avoids a JSON.stringify + disk write per character.
let saveTimer: ReturnType<typeof setTimeout> | undefined;
function saveParams(params: BuildingParams) {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(params));
    } catch {
      /* storage unavailable (private mode / quota) — non-fatal */
    }
  }, 300);
}

export type ViewMode = "3d" | "2d";

interface AppState {
  params: BuildingParams;
  /** Household preset driving the room program, or "custom" once hand-edited. */
  preset: ActivePreset;
  familyKids: number;
  result: GenerationResult | null;
  /** Previous plans (newest first) so a worse regenerate can be reverted. */
  history: GenerationResult[];
  /** True when params changed after the current result was generated. */
  resultStale: boolean;
  isGenerating: boolean;
  /** Last generation error, shown in the workspace until the next attempt. */
  error: string | null;
  activeFloor: number;
  showMEP: boolean;
  selectedRoomId: string | null;
  viewMode: ViewMode;
  /** Results panel open. In the store so the 2D viewer can dodge it (zoom widget). */
  rightPanelOpen: boolean;

  setParams: (p: Partial<BuildingParams>) => void;
  applyPreset: (preset: HouseholdPreset) => void;
  setFamilyKids: (kids: number) => void;
  addRoom: (r: RoomInput) => void;
  updateRoom: (index: number, r: Partial<RoomInput>) => void;
  removeRoom: (index: number) => void;
  setResult: (r: GenerationResult | null) => void;
  /** Revert to the previous plan in history (no-op if none). */
  undoResult: () => void;
  setGenerating: (v: boolean) => void;
  setError: (msg: string | null) => void;
  setActiveFloor: (f: number) => void;
  toggleMEP: () => void;
  setSelectedRoom: (id: string | null) => void;
  setViewMode: (m: ViewMode) => void;
  setRightPanelOpen: (v: boolean) => void;
}

const _initialParams = loadParams();
const _preset = deriveActivePreset(_initialParams.rooms, loadPreset());

export const useStore = create<AppState>((set) => ({
  params: _initialParams,
  preset: _preset.preset,
  familyKids: _preset.familyKids,
  result: null,
  history: [],
  resultStale: false,
  isGenerating: false,
  error: null,
  activeFloor: 1,
  showMEP: true,
  selectedRoomId: null,
  viewMode: "2d",
  rightPanelOpen: false,

  // Any change to params marks the current result as stale, but keeps it on
  // screen — wiping it on every keystroke would destroy the plan the user is
  // viewing. The UI shows a "regenerate" hint while resultStale is true.
  setParams: (p) =>
    set((s) => {
      const params = { ...s.params, ...p };
      saveParams(params);
      return { params, resultStale: s.result !== null };
    }),

  // Picking a preset replaces the whole room program with a sane, complete one.
  applyPreset: (preset) =>
    set((s) => {
      const params = { ...s.params, rooms: buildPresetRooms(preset, s.familyKids) };
      saveParams(params);
      savePreset(preset, s.familyKids);
      return { params, preset, resultStale: s.result !== null };
    }),

  // Only meaningful for the family preset; rebuilds its bedroom count live.
  setFamilyKids: (kids) =>
    set((s) => {
      const familyKids = Math.max(1, Math.min(4, Math.round(kids)));
      const next: Partial<AppState> = { familyKids };
      if (s.preset === "family") {
        const params = { ...s.params, rooms: buildPresetRooms("family", familyKids) };
        saveParams(params);
        next.params = params;
        next.resultStale = s.result !== null;
      }
      savePreset(s.preset, familyKids);
      return next;
    }),

  // Manual room edits move the program off any preset and onto "custom". Only
  // params are persisted (debounced); "custom" is re-derived on load, so rapid
  // keystrokes collapse to a single write instead of one per character.
  addRoom: (r) =>
    set((s) => {
      const params = { ...s.params, rooms: [...s.params.rooms, r] };
      saveParams(params);
      return { params, preset: "custom", resultStale: s.result !== null };
    }),

  updateRoom: (index, r) =>
    set((s) => {
      const rooms = [...s.params.rooms];
      rooms[index] = { ...rooms[index], ...r };
      const params = { ...s.params, rooms };
      saveParams(params);
      return { params, preset: "custom", resultStale: s.result !== null };
    }),

  removeRoom: (index) =>
    set((s) => {
      const params = {
        ...s.params,
        rooms: s.params.rooms.filter((_, i) => i !== index),
      };
      saveParams(params);
      return { params, preset: "custom", resultStale: s.result !== null };
    }),

  setResult: (r) =>
    set((s) => ({
      result: r,
      // Push the outgoing plan so a regenerate can be reverted (cap the depth).
      history: r && s.result ? [s.result, ...s.history].slice(0, 8) : s.history,
      resultStale: false,
      selectedRoomId: null,
    })),
  undoResult: () =>
    set((s) => {
      if (s.history.length === 0) return {};
      const [prev, ...rest] = s.history;
      return { result: prev, history: rest, resultStale: false, selectedRoomId: null };
    }),
  setGenerating: (v) => set({ isGenerating: v }),
  setError: (msg) => set({ error: msg }),
  setActiveFloor: (f) => set({ activeFloor: f }),
  toggleMEP: () => set((s) => ({ showMEP: !s.showMEP })),
  setSelectedRoom: (id) => set({ selectedRoomId: id }),
  setViewMode: (m) => set({ viewMode: m }),
  setRightPanelOpen: (v) => set({ rightPanelOpen: v }),
}));
