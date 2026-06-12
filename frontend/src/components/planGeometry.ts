import type { GenerationResult, RoomLayout } from "../types";

export interface BBox {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

export function floorRooms(result: GenerationResult | null, floor: number): RoomLayout[] {
  return result ? result.rooms.filter((r) => r.floor === floor) : [];
}

export function roomsBBox(rooms: RoomLayout[]): BBox | null {
  if (!rooms.length) return null;
  return {
    minX: Math.min(...rooms.map((r) => r.x)),
    maxX: Math.max(...rooms.map((r) => r.x + r.width)),
    minY: Math.min(...rooms.map((r) => r.y)),
    maxY: Math.max(...rooms.map((r) => r.y + r.depth)),
  };
}

/**
 * Defensive clamp shared by the 2D and 3D renderers: keep a door/window
 * inside its wall even if the backend emitted an overflowing position.
 */
export function clampPos(position: number, openingW: number, wallLen: number): number {
  return Math.max(0, Math.min(position, Math.max(0, wallLen - openingW)));
}
