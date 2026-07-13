import type { ComplianceIssue } from "../types";

// INV-2 (areas short of request) and INV-9 (below minimum usable dimension)
// are the engine's two "does not fit" signals. On one floor the honest fix is
// a second one — the classic family-with-3-4-kids scenario. Data-driven: the
// hint appears only when the checkers actually flagged a squeeze, never on an
// assumption about the program.
const SQUEEZE_RULE = /^INV-(2|9)-/;

export function needsSecondFloorHint(issues: ComplianceIssue[], floors: number): boolean {
  if (floors !== 1) return false;
  return issues.some((i) => i.severity === "ERROR" && SQUEEZE_RULE.test(i.rule_id));
}
