// Shared room-type palette: muted tones for 3D materials,
// brighter variants for 2D plan fills on the dark blueprint background.
export const ROOM_COLORS: Record<string, string> = {
  bedroom: "#4a7c8e",
  living_room: "#6b7a5c",
  kitchen: "#8e6b4a",
  bathroom: "#4a6b8e",
  toilet: "#4a6b8e",
  hallway: "#7a7a7a",
  utility: "#5c5c4a",
  garage: "#5c4a4a",
};

export const ROOM_FILL_2D: Record<string, string> = {
  bedroom: "#5fa8c4",
  living_room: "#93b06b",
  kitchen: "#c79a63",
  bathroom: "#6aa0d8",
  toilet: "#6aa0d8",
  hallway: "#9aa3ad",
  utility: "#b0a96a",
  garage: "#b07a6a",
};

export const DEFAULT_ROOM_COLOR = "#607080";
export const DEFAULT_FILL_2D = "#8aa0b8";

// Selected-room highlight shared by both viewers (brand-500 + lighter accent)
export const SELECTION_COLOR = "#3b82f6";
export const SELECTION_ACCENT = "#60a5fa";

// MEP clash marker colors; LOW falls back to MEDIUM
export const SEVERITY_COLORS: Record<string, string> = {
  HIGH: "#ef4444",
  MEDIUM: "#f59e0b",
};
