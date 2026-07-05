import type { TFunction } from "i18next";
import type { RoomType } from "../types";

// The backend stores either a user's custom room name or the English-title
// default of the type ("living_room" → "Living Room"). There is no flag to tell
// them apart, so a name equal to that default is treated as generated and
// localized from room_type via the shared `roomTypes.*` keys; any other name is
// the user's own words and shown verbatim.
function defaultEnglishName(roomType: RoomType): string {
  return roomType
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function roomDisplayName(room: { room_type: RoomType; name: string }, t: TFunction): string {
  if (room.name && room.name !== defaultEnglishName(room.room_type)) return room.name;
  return t(`roomTypes.${room.room_type}`);
}
