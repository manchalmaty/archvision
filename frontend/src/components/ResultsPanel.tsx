import { useState } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { useStore } from "../store/useStore";
import { ifcDownloadUrl, pdfReportUrl, shareUrl } from "../api/client";
import { exportPlanPng } from "./planExport";
import { Chevron, Reveal } from "./disclosure";

type Tab = "ANALYSIS" | "MEP" | "EXPORT";

function planQualityScore(result: import("../types").GenerationResult): {
  score: number;
  labelKey: string;
  color: string;
} {
  let issueScore = 100;
  const high = result.mep_conflicts.filter((c) => c.severity === "HIGH").length;
  const med = result.mep_conflicts.filter((c) => c.severity === "MEDIUM").length;
  const errors = result.compliance_issues.filter((i) => i.severity === "ERROR").length;
  const warns = result.compliance_issues.filter((i) => i.severity === "WARNING").length;
  issueScore -= Math.min(high * 5, 30);
  issueScore -= Math.min(med * 2, 10);
  issueScore -= errors * 10;
  issueScore -= warns * 3;
  issueScore = Math.max(0, issueScore);
  // Fold in daylight so the headline score reflects its own insolation metric:
  // a clean but poorly-lit plan should not read the same as a clean, sunny one.
  const insol = result.insolation_score ?? 100;
  const score = Math.round(0.7 * issueScore + 0.3 * insol);
  if (score >= 85) return { score, labelKey: "results.qualityGood", color: "#15803d" };
  if (score >= 65) return { score, labelKey: "results.qualityFair", color: "#a16207" };
  return { score, labelKey: "results.qualityReview", color: "#dc2626" };
}

function Accordion({
  title,
  badge,
  defaultOpen = false,
  children,
}: {
  title: string;
  badge?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-surface-border dim-rule">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between gap-2 py-[11px] px-1 rounded-md hover:bg-slate-50 transition-colors group"
      >
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500 group-hover:text-slate-700 transition-colors">
          {title}
        </span>
        <span className="flex items-center gap-2 text-slate-400">
          {badge}
          <Chevron open={open} />
        </span>
      </button>
      <Reveal open={open}>
        <div className="pb-3.5 pt-0.5">{children}</div>
      </Reveal>
    </div>
  );
}

// A tiny status pill — green tick when clean, red count when there are issues.
// Color carries the status (Vercel/Linear), so a collapsed section still reads.
function StatusBadge({ count }: { count: number }) {
  const ok = count === 0;
  return ok ? (
    <span className="inline-flex items-center justify-center min-w-[18px] rounded-full px-1.5 py-px bg-emerald-50 border border-emerald-300 text-emerald-700">
      <svg
        viewBox="0 0 12 12"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="w-3 h-3"
      >
        <path d="M2.5 6.5l2.5 2.5 4.5-5" />
      </svg>
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 min-w-[18px] justify-center rounded-full px-1.5 py-px bg-red-50 border border-red-200 text-red-700 text-[11px] font-bold">
      <svg
        viewBox="0 0 12 12"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="w-3 h-3"
      >
        <path d="M6 1.2L11 10H1L6 1.2z" />
        <path d="M6 4.8v2.4M6 8.9v.05" />
      </svg>
      {count}
    </span>
  );
}

function GeoCard() {
  const { t } = useTranslation();
  const { result } = useStore();
  if (!result) return null;
  const g = result.geo_climate;
  const items = [
    { label: t("results.frostDepth"), value: `${g.frost_depth_m} m` },
    { label: t("results.seismicZone"), value: String(g.seismic_zone) },
    { label: t("results.wallThickness"), value: `${g.wall_thickness_mm} mm` },
    { label: t("results.insulationThickness"), value: `${g.insulation_thickness_mm} mm` },
    { label: t("results.snowLoad"), value: `${g.snow_load_kpa} kPa` },
    { label: t("results.windLoad"), value: `${g.wind_load_kpa} kPa` },
    { label: t("daylight.score"), value: `${Math.round(result.insolation_score)}/100` },
  ];
  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 6 }}>
        {items.map(({ label, value }) => (
          <div key={label} style={{ background: "#fffdf8", borderRadius: 8, padding: "8px 10px" }}>
            <p style={{ fontSize: 11, color: "#7c7768", marginBottom: 3 }}>{label}</p>
            <p style={{ fontSize: 14, fontFamily: "monospace", color: "#33302a", fontWeight: 600 }}>
              {value}
            </p>
          </div>
        ))}
      </div>
      <div style={{ background: "#fffdf8", borderRadius: 8, padding: "8px 10px" }}>
        <p style={{ fontSize: 11, color: "#7c7768", marginBottom: 3 }}>
          {t("results.foundationType")}
        </p>
        <p style={{ fontSize: 13, color: "#33302a" }}>{g.foundation_type}</p>
      </div>
    </div>
  );
}

// The headline figure — always visible, framed as the drawing sheet's title
// block (штамп): thick outer frame, machine-print figure, data cells below.
// Ink-coloured (color is reserved for status), local currency primary.
function CostHero() {
  const { t } = useTranslation();
  const { result } = useStore();
  if (!result) return null;
  const c = result.cost_estimate;
  const usd = `$${c.total_cost_usd.toLocaleString()}`;
  const local = `${c.total_cost_local.toLocaleString()} ${c.currency}`;
  const isUsd = c.currency === "USD";
  const area = result.rooms.reduce((s, r) => s + r.width * r.depth, 0);
  const floors = new Set(result.rooms.map((r) => r.floor)).size;
  const ref = result.project_id.slice(0, 8).toUpperCase();
  const cells = [
    { label: t("results.stampArea"), value: `${Math.round(area)} m²` },
    { label: t("results.stampFloors"), value: String(floors) },
    { label: t("results.stampRef"), value: ref },
  ];
  return (
    <div className="stamp-frame mt-1 mb-4" key={result.project_id}>
      <div className="px-3 pt-2.5 pb-3">
        <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.08em] mb-1.5">
          {t("results.costEstimate")}
        </p>
        <p
          className="font-mono font-bold text-slate-900 leading-none tracking-tight text-[27px]"
          style={{ animation: "fade-up 0.35s ease-out" }}
        >
          {isUsd ? usd : local}
        </p>
        {!isUsd && (
          <p
            className="font-mono text-[12px] text-slate-400 mt-1.5"
            style={{ animation: "fade-up 0.35s ease-out 0.06s backwards" }}
          >
            ≈ {usd}
          </p>
        )}
      </div>
      <div className="grid grid-cols-3">
        {cells.map(({ label, value }, i) => (
          <div key={label} className={`stamp-cell border-t ${i > 0 ? "border-l" : ""}`}>
            <p className="text-[9px] text-slate-500 uppercase tracking-[0.06em] mb-0.5">{label}</p>
            <p className="font-mono text-[11.5px] text-slate-800 truncate">{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function CostBreakdown() {
  const { t } = useTranslation();
  const { result } = useStore();
  if (!result) return null;
  const c = result.cost_estimate;
  // Same currency as the hero above — a $ breakdown under a KZT total reads
  // like two different estimates.
  const rate = c.total_cost_usd > 0 ? c.total_cost_local / c.total_cost_usd : 1;
  const fmt = (usd: number) =>
    c.currency === "USD"
      ? `$${usd.toLocaleString()}`
      : `${Math.round(usd * rate).toLocaleString()} ${c.currency}`;
  return (
    <div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2, marginBottom: 10 }}>
        {Object.entries(c.breakdown).map(([k, v]) => (
          <div
            key={k}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "5px 2px",
              borderBottom: "1px solid #eae5d9",
            }}
          >
            <span style={{ fontSize: 13, color: "#615c4f", textTransform: "capitalize" }}>
              {k.replace("_usd", "").replace(/_/g, " ")}
            </span>
            <span
              style={{ fontSize: 13, fontFamily: "monospace", color: "#4a463c", fontWeight: 600 }}
            >
              {fmt(v as number)}
            </span>
          </div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
        {[
          { label: t("results.concrete"), value: `${c.concrete_m3} m³` },
          { label: t("results.brick"), value: `${c.brick_m3} m³` },
          { label: t("results.insulationArea"), value: `${c.insulation_m2} m²` },
        ].map(({ label, value }) => (
          <div
            key={label}
            style={{
              background: "#f5f2ea",
              borderRadius: 6,
              padding: "7px 4px",
              textAlign: "center",
            }}
          >
            <p style={{ fontSize: 10, color: "#7c7768", marginBottom: 3 }}>{label}</p>
            <p style={{ fontSize: 12, fontFamily: "monospace", color: "#33302a" }}>{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function ComplianceCard() {
  const { t } = useTranslation();
  const { result } = useStore();
  if (!result) return null;
  const issues = result.compliance_issues;

  if (issues.length === 0) {
    // Traffic light, not a blanket "all codes pass": we check areas and
    // geometry, a licensed specialist checks the actual building codes.
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            background: "#ecfdf5",
            border: "1px solid #166534",
            borderRadius: 20,
            padding: "4px 12px",
            fontSize: 13,
            color: "#15803d",
            alignSelf: "flex-start",
          }}
        >
          ✓ {t("results.precheckPassed")}
        </div>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            background: "#fffbeb",
            border: "1px solid #d97706",
            borderRadius: 20,
            padding: "4px 12px",
            fontSize: 13,
            color: "#b45309",
            alignSelf: "flex-start",
          }}
        >
          ⚠ {t("results.codesNeedExpert")}
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {issues.map((issue) => (
        <div
          key={issue.rule_id}
          style={{ background: "#fffdf8", borderRadius: 8, padding: "8px 10px" }}
        >
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              borderRadius: 20,
              padding: "2px 10px",
              fontSize: 11,
              fontWeight: 700,
              ...(issue.severity === "ERROR"
                ? { background: "#fef2f2", border: "1px solid #dc2626", color: "#b91c1c" }
                : { background: "#fff7ed", border: "1px solid #ea580c", color: "#c2410c" }),
            }}
          >
            {issue.severity}
          </span>
          <p style={{ fontSize: 13, color: "#4a463c", marginTop: 5 }}>{issue.description}</p>
          {issue.suggested_fix && (
            <p style={{ fontSize: 12, color: "#7c7768", marginTop: 3 }}>→ {issue.suggested_fix}</p>
          )}
        </div>
      ))}
    </div>
  );
}

function WarningsSection() {
  const { t } = useTranslation();
  const { result } = useStore();
  if (!result || result.warnings.length === 0) return null;
  return (
    <Accordion title={t("results.warnings", { count: result.warnings.length })} defaultOpen>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {result.warnings.map((w, i) => (
          <p key={i} style={{ fontSize: 13, color: "#b45309" }}>
            ⚠ {w}
          </p>
        ))}
      </div>
    </Accordion>
  );
}

function MEPTab() {
  const { t } = useTranslation();
  const { result } = useStore();
  if (!result) return null;
  const conflicts = result.mep_conflicts;

  const disclaimer = (
    <div
      style={{
        background: "#ecfeff",
        border: "1px solid #06b6d4",
        borderRadius: 8,
        padding: "8px 10px",
        fontSize: 11,
        lineHeight: 1.4,
        color: "#155e75",
        marginBottom: 8,
      }}
    >
      {t("results.mepDraftNote")}
    </div>
  );

  if (conflicts.length === 0) {
    // Status badge (icon + title + scope subtitle): the subtitle names what
    // WAS checked — a bare "no clashes" would imply disciplines we don't do.
    return (
      <div style={{ paddingTop: 8 }}>
        {disclaimer}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            background: "#fffdf8",
            border: "1px solid #dcd7c9",
            borderRadius: 8,
            padding: "12px 14px",
            marginTop: 4,
          }}
        >
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 30,
              height: 30,
              borderRadius: "50%",
              background: "#ecfdf5",
              border: "1.5px solid #15803d",
              color: "#15803d",
              flexShrink: 0,
            }}
          >
            <svg
              viewBox="0 0 12 12"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.8}
              strokeLinecap="round"
              strokeLinejoin="round"
              width={14}
              height={14}
            >
              <path d="M2.5 6.5l2.5 2.5 4.5-5" />
            </svg>
          </span>
          <div>
            <p style={{ fontSize: 13, fontWeight: 600, color: "#33302a" }}>
              {t("results.noClashes")}
            </p>
            <p style={{ fontSize: 11, color: "#7c7768", marginTop: 2 }}>
              {t("results.mepCheckedScope")}
            </p>
          </div>
        </div>
      </div>
    );
  }

  const high = conflicts.filter((c) => c.severity === "HIGH").length;
  const med = conflicts.filter((c) => c.severity === "MEDIUM").length;
  const low = conflicts.filter((c) => !["HIGH", "MEDIUM"].includes(c.severity)).length;

  const chipStyle = (sev: string) => {
    if (sev === "HIGH")
      return { background: "#fef2f2", border: "1px solid #dc2626", color: "#b91c1c" };
    if (sev === "MEDIUM")
      return { background: "#fff7ed", border: "1px solid #ea580c", color: "#c2410c" };
    return { background: "#fefce8", border: "1px solid #ca8a04", color: "#a16207" };
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, paddingTop: 8 }}>
      {disclaimer}
      {/* Summary chips */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
        {high > 0 && (
          <span
            style={{
              ...chipStyle("HIGH"),
              borderRadius: 12,
              padding: "3px 10px",
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            HIGH: {high}
          </span>
        )}
        {med > 0 && (
          <span
            style={{
              ...chipStyle("MEDIUM"),
              borderRadius: 12,
              padding: "3px 10px",
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            MEDIUM: {med}
          </span>
        )}
        {low > 0 && (
          <span
            style={{
              ...chipStyle("LOW"),
              borderRadius: 12,
              padding: "3px 10px",
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            LOW: {low}
          </span>
        )}
        <span style={{ fontSize: 12, color: "#7c7768", alignSelf: "center" }}>
          {t("results.total")}: {conflicts.length}
        </span>
      </div>

      {/* Conflict list */}
      {conflicts.map((c) => {
        // Locale files are the single source of hint types; unknown conflict
        // types fall back to the generic guidance.
        const hint = t(`mepHints.${c.conflict_type}`, {
          defaultValue: t("mepHints.default"),
        });
        return (
          <div
            key={c.conflict_id}
            style={{ ...chipStyle(c.severity), borderRadius: 8, padding: "8px 10px" }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 4,
              }}
            >
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                }}
              >
                {c.severity}
              </span>
              <span style={{ fontSize: 11, fontFamily: "monospace", opacity: 0.6 }}>
                ({c.location_x.toFixed(1)}, {c.location_y.toFixed(1)}, {c.location_z.toFixed(1)})
              </span>
            </div>
            <p style={{ fontSize: 13 }}>{c.description}</p>
            {hint && (
              <details style={{ marginTop: 6 }}>
                <summary
                  style={{ fontSize: 11, color: "#615c4f", cursor: "pointer", userSelect: "none" }}
                >
                  {t("results.howToFix")}
                </summary>
                <p style={{ fontSize: 12, color: "#4a463c", marginTop: 4, lineHeight: 1.5 }}>
                  {hint}
                </p>
              </details>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ExportTab() {
  const { t, i18n } = useTranslation();
  const { result } = useStore();
  const viewMode = useStore((s) => s.viewMode);
  if (!result) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingTop: 8 }}>
      <a
        href={ifcDownloadUrl(result.project_id)}
        download={`archvision_${result.project_id.slice(0, 8)}.ifc`}
        className="btn-secondary"
        style={{ textAlign: "center", fontSize: 14, padding: "11px", display: "block" }}
      >
        {t("results.downloadIfc")}
      </a>
      <a
        href={pdfReportUrl(result.project_id, i18n.resolvedLanguage)}
        download={`archvision_${result.project_id.slice(0, 8)}.pdf`}
        className="btn-secondary"
        style={{ textAlign: "center", fontSize: 14, padding: "11px", display: "block" }}
      >
        {t("results.exportPdf")}
      </a>
      {/* Exporter only exists while the 2D svg is mounted */}
      {viewMode === "2d" && (
        <button
          onClick={exportPlanPng}
          className="btn-secondary"
          style={{ textAlign: "center", fontSize: 14, padding: "11px", display: "block" }}
        >
          {t("results.exportPng")}
        </button>
      )}
      <button
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(shareUrl(result.project_id));
            toast.success(t("results.linkCopied"));
          } catch {
            toast.error(t("results.linkCopyFailed"));
          }
        }}
        className="btn-secondary"
        style={{ textAlign: "center", fontSize: 14, padding: "11px", display: "block" }}
      >
        {t("results.copyLink")}
      </button>
      <p style={{ fontSize: 12, color: "#a39e90", textAlign: "center", marginTop: 8 }}>
        {t("results.projectId")}{" "}
        <span style={{ fontFamily: "monospace", color: "#7c7768" }}>
          {result.project_id.slice(0, 8)}
        </span>
      </p>
    </div>
  );
}

interface Props {
  onClose: () => void;
}

export function ResultsPanel({ onClose }: Props) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("ANALYSIS");
  const { result, history, undoResult } = useStore();
  if (!result) return null;

  const tabs: { id: Tab; label: string }[] = [
    { id: "ANALYSIS", label: t("results.tabAnalysis") },
    {
      id: "MEP",
      label: `MEP${result.mep_conflicts.length > 0 ? ` (${result.mep_conflicts.length})` : ""}`,
    },
    { id: "EXPORT", label: t("results.tabExport") },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Panel header */}
      <div className="flex-shrink-0 border-b border-surface-border bg-surface-panel">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "10px 16px 0",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: "#a39e90",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
              }}
            >
              {t("results.title")}
            </span>
            {(() => {
              const q = planQualityScore(result);
              return (
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    color: q.color,
                    border: `1px solid ${q.color}40`,
                    borderRadius: 10,
                    padding: "1px 8px",
                    background: `${q.color}15`,
                  }}
                >
                  {t(q.labelKey)} · {q.score}/100
                </span>
              );
            })()}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
            {history.length > 0 && (
              <button
                onClick={undoResult}
                className="flex items-center gap-1 px-2 py-0.5 rounded-[7px] border border-surface-border text-slate-500 text-xs font-semibold transition-all duration-150 hover:text-brand-600 hover:border-brand-100 hover:bg-brand-50"
                title={t("results.undoVersion")}
              >
                ↶ {history.length}
              </button>
            )}
            <button
              onClick={onClose}
              className="px-0.5 text-xl leading-none text-slate-400 hover:text-slate-600 transition-colors"
              title={t("results.closePanel")}
            >
              ×
            </button>
          </div>
        </div>
        {/* Tabs */}
        <div className="flex px-4 pt-1.5">
          {tabs.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`px-3.5 py-1.5 text-xs font-semibold tracking-[0.04em] border-b-2 transition-colors duration-150 ${
                tab === id
                  ? "border-brand-500 text-slate-800"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px" }}>
        {tab === "ANALYSIS" && (
          <div>
            <WarningsSection />
            <CostHero />
            <Accordion title={t("results.costBreakdown")}>
              <CostBreakdown />
            </Accordion>
            <Accordion title={t("results.geoClimate")}>
              <GeoCard />
            </Accordion>
            <Accordion
              title={t("results.compliance", { count: result.compliance_issues.length })}
              badge={<StatusBadge count={result.compliance_issues.length} />}
              defaultOpen={result.compliance_issues.length > 0}
            >
              <ComplianceCard />
            </Accordion>
          </div>
        )}
        {tab === "MEP" && <MEPTab />}
        {tab === "EXPORT" && <ExportTab />}
      </div>
    </div>
  );
}
