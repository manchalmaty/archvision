// Shared room-type palette — ONE set of pastel fills for both viewers (the 3D
// scene sits on the same warm paper as the 2D plan since release 8).
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

export const DEFAULT_FILL_2D = "#8aa0b8";

// Selected-room highlight shared by both viewers (brand-500 + lighter accent)
export const SELECTION_COLOR = "#3b82f6";
export const SELECTION_ACCENT = "#60a5fa";

// MEP clash marker colors; LOW falls back to MEDIUM
export const SEVERITY_COLORS: Record<string, string> = {
  HIGH: "#ef4444",
  MEDIUM: "#f59e0b",
};
