import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { useStore, deriveActivePreset } from "./useStore";
import { buildPresetRooms } from "../presets";
import type { GenerationResult } from "../types";

const fakeResult = { project_id: "test-id", rooms: [] } as unknown as GenerationResult;

// Environment-independent localStorage stub (the jsdom global lacks methods
// under this vitest version, and the store only needs get/set).
const backing = new Map<string, string>();
const setItemSpy = vi.fn((k: string, v: string) => void backing.set(k, v));
vi.stubGlobal("localStorage", {
  getItem: (k: string) => backing.get(k) ?? null,
  setItem: setItemSpy,
  removeItem: (k: string) => void backing.delete(k),
});

// Snapshot of the pristine store (state + actions) to restore between tests.
const initialState = useStore.getState();

beforeEach(() => {
  useStore.setState(initialState, true);
  backing.clear();
  setItemSpy.mockClear();
});

describe("param mutators", () => {
  it("addRoom appends a room", () => {
    const before = useStore.getState().params.rooms.length;
    useStore.getState().addRoom({ room_type: "garage", area_m2: 18 });
    const rooms = useStore.getState().params.rooms;
    expect(rooms).toHaveLength(before + 1);
    expect(rooms[rooms.length - 1].room_type).toBe("garage");
  });

  it("updateRoom merges fields", () => {
    useStore.getState().updateRoom(0, { area_m2: 33 });
    expect(useStore.getState().params.rooms[0].area_m2).toBe(33);
  });

  it("removeRoom deletes by index", () => {
    const before = useStore.getState().params.rooms.length;
    useStore.getState().removeRoom(0);
    expect(useStore.getState().params.rooms).toHaveLength(before - 1);
  });

  it("setParams merges partial params", () => {
    useStore.getState().setParams({ floors: 3, plot_width_m: 12 });
    const { params } = useStore.getState();
    expect(params.floors).toBe(3);
    expect(params.plot_width_m).toBe(12);
  });
});

describe("stale-result tracking", () => {
  it("does not mark stale when there is no result", () => {
    useStore.getState().setParams({ floors: 2 });
    expect(useStore.getState().resultStale).toBe(false);
  });

  it("keeps result visible but marks it stale on any param change", () => {
    useStore.getState().setResult(fakeResult);
    useStore.getState().updateRoom(0, { name: "X" });
    const s = useStore.getState();
    expect(s.result).toBe(fakeResult); // result must NOT be wiped
    expect(s.resultStale).toBe(true);
  });

  it("setResult clears staleness and room selection", () => {
    useStore.getState().setResult(fakeResult);
    useStore.getState().setSelectedRoom("room-1");
    useStore.getState().setParams({ floors: 2 });
    useStore.getState().setResult(fakeResult);
    const s = useStore.getState();
    expect(s.resultStale).toBe(false);
    expect(s.selectedRoomId).toBeNull();
  });
});

describe("localStorage persistence", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("debounces writes: nothing immediately, saved after 300ms", () => {
    vi.useFakeTimers();
    useStore.getState().setParams({ floors: 4 });
    expect(localStorage.getItem("archvision_params_v1")).toBeNull();

    vi.advanceTimersByTime(350);
    const saved = JSON.parse(localStorage.getItem("archvision_params_v1")!);
    expect(saved.floors).toBe(4);
  });

  it("collapses rapid keystrokes into one write", () => {
    vi.useFakeTimers();
    for (let i = 0; i < 10; i++) {
      useStore.getState().updateRoom(0, { name: "Room".slice(0, (i % 4) + 1) });
      vi.advanceTimersByTime(50); // faster than the 300ms debounce
    }
    vi.advanceTimersByTime(350);
    expect(setItemSpy).toHaveBeenCalledTimes(1);
  });
});

describe("deriveActivePreset", () => {
  it("keeps the stored preset when rooms still match its program", () => {
    const rooms = buildPresetRooms("couple");
    expect(
      deriveActivePreset(rooms, { preset: "couple", familyKids: 2, garage: false })
    ).toEqual({ preset: "couple", familyKids: 2, garage: false });
  });

  it("re-derives custom when stored rooms no longer match the preset", () => {
    const rooms = buildPresetRooms("couple").slice(0, 3); // hand-edited away
    expect(
      deriveActivePreset(rooms, { preset: "couple", familyKids: 2, garage: false }).preset
    ).toBe("custom");
  });

  it("treats a hand-named preset room as custom", () => {
    const rooms = buildPresetRooms("single");
    rooms[0] = { ...rooms[0], name: "Studio" };
    expect(
      deriveActivePreset(rooms, { preset: "single", familyKids: 2, garage: false }).preset
    ).toBe("custom");
  });

  it("matches the family program for the stored kid count", () => {
    const rooms = buildPresetRooms("family", 3);
    expect(
      deriveActivePreset(rooms, { preset: "family", familyKids: 3, garage: false }).preset
    ).toBe("family");
    expect(
      deriveActivePreset(rooms, { preset: "family", familyKids: 2, garage: false }).preset
    ).toBe("custom");
  });

  it("passes through an already-custom program untouched", () => {
    const rooms = buildPresetRooms("rental");
    expect(
      deriveActivePreset(rooms, { preset: "custom", familyKids: 2, garage: false }).preset
    ).toBe("custom");
  });

  it("matches the preset program with the garage modifier on", () => {
    const rooms = buildPresetRooms("couple", 2, true);
    expect(
      deriveActivePreset(rooms, { preset: "couple", familyKids: 2, garage: true }).preset
    ).toBe("couple");
    expect(
      deriveActivePreset(rooms, { preset: "couple", familyKids: 2, garage: false }).preset
    ).toBe("custom");
  });
});

describe("garage preset modifier", () => {
  it("appends one garage to the active preset program", () => {
    useStore.getState().applyPreset("couple");
    useStore.getState().setGarage(true);
    const rooms = useStore.getState().params.rooms;
    expect(rooms.filter((r) => r.room_type === "garage")).toHaveLength(1);
    expect(useStore.getState().preset).toBe("couple"); // still a preset, not custom
  });

  it("survives a preset switch", () => {
    useStore.getState().setGarage(true);
    useStore.getState().applyPreset("family");
    const rooms = useStore.getState().params.rooms;
    expect(rooms.some((r) => r.room_type === "garage")).toBe(true);
  });

  it("removes the garage when toggled off", () => {
    useStore.getState().setGarage(true);
    useStore.getState().setGarage(false);
    expect(useStore.getState().params.rooms.some((r) => r.room_type === "garage")).toBe(false);
  });

  it("does not duplicate a hand-added garage in custom mode", () => {
    useStore.getState().addRoom({ room_type: "garage", area_m2: 30 }); // → custom
    useStore.getState().setGarage(true);
    const rooms = useStore.getState().params.rooms;
    expect(rooms.filter((r) => r.room_type === "garage")).toHaveLength(1);
    expect(rooms.find((r) => r.room_type === "garage")!.area_m2).toBe(30); // untouched
  });

  it("keeps custom hand-edits when toggling the garage off", () => {
    useStore.getState().updateRoom(0, { area_m2: 33 }); // → custom
    useStore.getState().setGarage(true);
    useStore.getState().setGarage(false);
    const s = useStore.getState();
    expect(s.preset).toBe("custom");
    expect(s.params.rooms[0].area_m2).toBe(33);
    expect(s.params.rooms.some((r) => r.room_type === "garage")).toBe(false);
  });
});
