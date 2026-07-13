import { describe, expect, it } from "vitest";
import { needsSecondFloorHint } from "./secondFloorHint";
import type { ComplianceIssue } from "../types";

const issue = (rule_id: string, severity: ComplianceIssue["severity"] = "ERROR") => ({
  rule_id,
  description: "x",
  severity,
});

describe("needsSecondFloorHint", () => {
  it("fires on a min-dimension ERROR at one floor", () => {
    expect(needsSecondFloorHint([issue("INV-9-NARROW")], 1)).toBe(true);
  });

  it("fires on an area-shortfall ERROR at one floor", () => {
    expect(needsSecondFloorHint([issue("INV-2-AREA")], 1)).toBe(true);
  });

  it("stays silent when the plan already has two floors", () => {
    expect(needsSecondFloorHint([issue("INV-9-NARROW")], 2)).toBe(false);
  });

  it("stays silent on other rules and on warnings", () => {
    expect(needsSecondFloorHint([issue("INV-10-GARAGE", "WARNING")], 1)).toBe(false);
    expect(needsSecondFloorHint([issue("INV-4-TRANSIT")], 1)).toBe(false);
    expect(needsSecondFloorHint([issue("SITE-1-S")], 1)).toBe(false);
    expect(needsSecondFloorHint([issue("INV-9-NARROW", "WARNING")], 1)).toBe(false);
  });

  it("stays silent on a clean plan", () => {
    expect(needsSecondFloorHint([], 1)).toBe(false);
  });
});
