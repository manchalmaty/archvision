import { create } from "zustand";
import type { BuildingParams, GenerationResult, RoomInput } from "../types";

const STORAGE_KEY = "archvision_params_v1";

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
  result: GenerationResult | null;
  /** True when params changed after the current result was generated. */
  resultStale: boolean;
  isGenerating: boolean;
  /** Last generation error, shown in the workspace until the next attempt. */
  error: string | null;
  activeFloor: number;
  showMEP: boolean;
  selectedRoomId: string | null;
  viewMode: ViewMode;

  setParams: (p: Partial<BuildingParams>) => void;
  addRoom: (r: RoomInput) => void;
  updateRoom: (index: number, r: Partial<RoomInput>) => void;
  removeRoom: (index: number) => void;
  setResult: (r: GenerationResult | null) => void;
  setGenerating: (v: boolean) => void;
  setError: (msg: string | null) => void;
  setActiveFloor: (f: number) => void;
  toggleMEP: () => void;
  setSelectedRoom: (id: string | null) => void;
  setViewMode: (m: ViewMode) => void;
}

export const useStore = create<AppState>((set) => ({
  params: loadParams(),
  result: null,
  resultStale: false,
  isGenerating: false,
  error: null,
  activeFloor: 1,
  showMEP: true,
  selectedRoomId: null,
  viewMode: "3d",

  // Any change to params marks the current result as stale, but keeps it on
  // screen — wiping it on every keystroke would destroy the plan the user is
  // viewing. The UI shows a "regenerate" hint while resultStale is true.
  setParams: (p) =>
    set((s) => {
      const params = { ...s.params, ...p };
      saveParams(params);
      return { params, resultStale: s.result !== null };
    }),

  addRoom: (r) =>
    set((s) => {
      const params = { ...s.params, rooms: [...s.params.rooms, r] };
      saveParams(params);
      return { params, resultStale: s.result !== null };
    }),

  updateRoom: (index, r) =>
    set((s) => {
      const rooms = [...s.params.rooms];
      rooms[index] = { ...rooms[index], ...r };
      const params = { ...s.params, rooms };
      saveParams(params);
      return { params, resultStale: s.result !== null };
    }),

  removeRoom: (index) =>
    set((s) => {
      const params = {
        ...s.params,
        rooms: s.params.rooms.filter((_, i) => i !== index),
      };
      saveParams(params);
      return { params, resultStale: s.result !== null };
    }),

  setResult: (r) => set({ result: r, resultStale: false, selectedRoomId: null }),
  setGenerating: (v) => set({ isGenerating: v }),
  setError: (msg) => set({ error: msg }),
  setActiveFloor: (f) => set({ activeFloor: f }),
  toggleMEP: () => set((s) => ({ showMEP: !s.showMEP })),
  setSelectedRoom: (id) => set({ selectedRoomId: id }),
  setViewMode: (m) => set({ viewMode: m }),
}));
