import type { RoomInput } from "./types";

// A household preset is a *preference* (different people, different programs) —
// but it doubles as input protection: instead of a manual list that drifts into
// duplicates and a missing kitchen, the user picks who will live here and gets a
// sane, complete room program. Manual editing stays available as advanced mode.
export type HouseholdPreset = "couple" | "family" | "single" | "rental";

// Shown in this order (by value for the typical ИЖС buyer).
export const PRESETS: HouseholdPreset[] = ["couple", "family", "single", "rental"];

export const FAMILY_KIDS_MIN = 1;
export const FAMILY_KIDS_MAX = 4;
export const FAMILY_KIDS_DEFAULT = 2;

/** Build a complete, invariant-friendly room program for a household preset. */
export function buildPresetRooms(preset: HouseholdPreset, kids = FAMILY_KIDS_DEFAULT): RoomInput[] {
  switch (preset) {
    case "single":
      return [
        { room_type: "living_room", area_m2: 18 },
        { room_type: "bedroom", area_m2: 12 },
        { room_type: "kitchen", area_m2: 9 },
        { room_type: "bathroom", area_m2: 4 },
        { room_type: "hallway", area_m2: 5 },
      ];
    case "couple":
      return [
        { room_type: "living_room", area_m2: 20 },
        { room_type: "bedroom", area_m2: 14 },
        { room_type: "kitchen", area_m2: 10 },
        { room_type: "bathroom", area_m2: 5 },
        { room_type: "toilet", area_m2: 2 },
        { room_type: "hallway", area_m2: 6 },
      ];
    case "family": {
      const n = Math.min(Math.max(Math.round(kids), FAMILY_KIDS_MIN), FAMILY_KIDS_MAX);
      const childBedrooms: RoomInput[] = Array.from({ length: n }, () => ({
        room_type: "bedroom" as const,
        area_m2: 11,
      }));
      return [
        { room_type: "living_room", area_m2: 24 },
        { room_type: "bedroom", area_m2: 15 }, // parents
        ...childBedrooms,
        { room_type: "kitchen", area_m2: 12 },
        { room_type: "bathroom", area_m2: 5 },
        { room_type: "toilet", area_m2: 2 },
        { room_type: "utility", area_m2: 4 },
        { room_type: "hallway", area_m2: 7 },
      ];
    }
    case "rental":
      // Two lettable bedrooms, compact shared spaces.
      return [
        { room_type: "living_room", area_m2: 18 },
        { room_type: "bedroom", area_m2: 12 },
        { room_type: "bedroom", area_m2: 12 },
        { room_type: "kitchen", area_m2: 9 },
        { room_type: "bathroom", area_m2: 4 },
        { room_type: "toilet", area_m2: 2 },
        { room_type: "hallway", area_m2: 6 },
      ];
  }
}
