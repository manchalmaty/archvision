import { describe, expect, it } from "vitest";
import en from "./en";
import kk from "./kk";
import ru from "./ru";

// Every locale must expose the exact same key tree: a key added to one file
// but not the others silently renders as the raw key path in the UI.
function keyPaths(obj: Record<string, unknown>, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) => {
    const path = prefix ? `${prefix}.${k}` : k;
    return v !== null && typeof v === "object"
      ? keyPaths(v as Record<string, unknown>, path)
      : [path];
  });
}

describe("locale key parity", () => {
  const enKeys = keyPaths(en).sort();

  it.each([
    ["ru", ru],
    ["kk", kk],
  ] as const)("%s matches en", (_name, locale) => {
    expect(keyPaths(locale).sort()).toEqual(enKeys);
  });

  it("en has no empty values", () => {
    const empty = keyPaths(en).filter((p) => {
      const v = p.split(".").reduce<unknown>((o, k) => (o as Record<string, unknown>)[k], en);
      return v === "";
    });
    expect(empty).toEqual([]);
  });
});
