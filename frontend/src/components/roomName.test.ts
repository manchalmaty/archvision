import { describe, expect, it } from "vitest";
import type { TFunction } from "i18next";
import { roomDisplayName } from "./roomName";

// Stub t: echoes the key so we can assert which i18n key was looked up.
const tStub = ((key: string) => key) as unknown as TFunction;

describe("roomDisplayName", () => {
  it("localizes a generated (default English) name via its roomTypes key", () => {
    expect(roomDisplayName({ room_type: "bedroom", name: "Bedroom" }, tStub)).toBe(
      "roomTypes.bedroom"
    );
  });

  it("localizes a multi-word default name", () => {
    expect(roomDisplayName({ room_type: "living_room", name: "Living Room" }, tStub)).toBe(
      "roomTypes.living_room"
    );
  });

  it("keeps a user custom name verbatim", () => {
    expect(roomDisplayName({ room_type: "bedroom", name: "Кабинет" }, tStub)).toBe("Кабинет");
  });
});
