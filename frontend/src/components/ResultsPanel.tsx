import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useStore } from "../store/useStore";
import { ifcDownloadUrl, pdfReportUrl } from "../api/client";

type Tab = "ANALYSIS" | "MEP" | "EXPORT";

function planQualityScore(result: import("../types").GenerationResult): {
  score: number;
  labelKey: string;
  color: string;
} {
  let score = 100;
  const high = result.mep_conflicts.filter((c) => c.severity === "HIGH").length;
  const med = result.mep_conflicts.filter((c) => c.severity === "MEDIUM").length;
  const errors = result.compliance_issues.filter((i) => i.severity === "ERROR").length;
  const warns = result.compliance_issues.filter((i) => i.severity === "WARNING").length;
  score -= Math.min(high * 5, 30);
  score -= Math.min(med * 2, 10);
  score -= errors * 10;
  score -= warns * 3;
  score = Math.max(0, score);
  if (score >= 85) return { score, labelKey: "results.qualityGood", color: "#6ee7b7" };
  if (score >= 65) return { score, labelKey: "results.qualityFair", color: "#fde047" };
  return { score, labelKey: "results.qualityReview", color: "#f87171" };
}

function Accordion({
  title,
  defaultOpen = true,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ borderBottom: "1px solid #1e2330", marginBottom: 2 }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          width: "100%",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "10px 0",
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "#94a3b8",
        }}
      >
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
          }}
        >
          {title}
        </span>
        <span
          style={{
            fontSize: 14,
            display: "inline-block",
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.2s",
          }}
        >
          ▾
        </span>
      </button>
      {open && <div style={{ paddingBottom: 14 }}>{children}</div>}
    </div>
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
  ];
  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 6 }}>
        {items.map(({ label, value }) => (
          <div key={label} style={{ background: "#161b27", borderRadius: 8, padding: "8px 10px" }}>
            <p style={{ fontSize: 11, color: "#64748b", marginBottom: 3 }}>{label}</p>
            <p style={{ fontSize: 14, fontFamily: "monospace", color: "#e2e8f0", fontWeight: 600 }}>
              {value}
            </p>
          </div>
        ))}
      </div>
      <div style={{ background: "#161b27", borderRadius: 8, padding: "8px 10px" }}>
        <p style={{ fontSize: 11, color: "#64748b", marginBottom: 3 }}>
          {t("results.foundationType")}
        </p>
        <p style={{ fontSize: 13, color: "#e2e8f0" }}>{g.foundation_type}</p>
      </div>
    </div>
  );
}

function CostCard() {
  const { t } = useTranslation();
  const { result } = useStore();
  if (!result) return null;
  const c = result.cost_estimate;
  return (
    <div>
      <div
        style={{
          textAlign: "center",
          marginBottom: 10,
          padding: "12px",
          background: "#161b27",
          borderRadius: 8,
        }}
      >
        <p
          style={{
            fontSize: 30,
            fontWeight: 700,
            color: "#fff",
            fontFamily: "monospace",
            lineHeight: 1.1,
          }}
        >
          ${c.total_cost_usd.toLocaleString()}
        </p>
        <p style={{ fontSize: 13, color: "#94a3b8", marginTop: 4 }}>
          ≈ {c.total_cost_local.toLocaleString()} {c.currency}
        </p>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2, marginBottom: 10 }}>
        {Object.entries(c.breakdown).map(([k, v]) => (
          <div
            key={k}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "5px 2px",
              borderBottom: "1px solid #1a1f2e",
            }}
          >
            <span style={{ fontSize: 13, color: "#94a3b8", textTransform: "capitalize" }}>
              {k.replace("_usd", "").replace(/_/g, " ")}
            </span>
            <span
              style={{ fontSize: 13, fontFamily: "monospace", color: "#cbd5e1", fontWeight: 600 }}
            >
              ${(v as number).toLocaleString()}
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
              background: "#161b27",
              borderRadius: 6,
              padding: "7px 4px",
              textAlign: "center",
            }}
          >
            <p style={{ fontSize: 10, color: "#64748b", marginBottom: 3 }}>{label}</p>
            <p style={{ fontSize: 12, fontFamily: "monospace", color: "#e2e8f0" }}>{value}</p>
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
    return (
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          background: "#052e16",
          border: "1px solid #166534",
          borderRadius: 20,
          padding: "4px 12px",
          fontSize: 13,
          color: "#6ee7b7",
        }}
      >
        {t("results.allRulesPassed")}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {issues.map((issue) => (
        <div
          key={issue.rule_id}
          style={{ background: "#161b27", borderRadius: 8, padding: "8px 10px" }}
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
                ? { background: "#450a0a", border: "1px solid #dc2626", color: "#fca5a5" }
                : { background: "#431407", border: "1px solid #ea580c", color: "#fdba74" }),
            }}
          >
            {issue.severity}
          </span>
          <p style={{ fontSize: 13, color: "#cbd5e1", marginTop: 5 }}>{issue.description}</p>
          {issue.suggested_fix && (
            <p style={{ fontSize: 12, color: "#64748b", marginTop: 3 }}>→ {issue.suggested_fix}</p>
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
          <p key={i} style={{ fontSize: 13, color: "#fbbf24" }}>
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

  if (conflicts.length === 0) {
    return (
      <div style={{ padding: "40px 16px", textAlign: "center" }}>
        <p style={{ fontSize: 36, marginBottom: 8 }}>✓</p>
        <p style={{ fontSize: 14, color: "#6ee7b7" }}>{t("results.noClashes")}</p>
      </div>
    );
  }

  const high = conflicts.filter((c) => c.severity === "HIGH").length;
  const med = conflicts.filter((c) => c.severity === "MEDIUM").length;
  const low = conflicts.filter((c) => !["HIGH", "MEDIUM"].includes(c.severity)).length;

  const chipStyle = (sev: string) => {
    if (sev === "HIGH")
      return { background: "#450a0a", border: "1px solid #dc2626", color: "#fca5a5" };
    if (sev === "MEDIUM")
      return { background: "#431407", border: "1px solid #ea580c", color: "#fdba74" };
    return { background: "#422006", border: "1px solid #ca8a04", color: "#fde047" };
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, paddingTop: 8 }}>
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
        <span style={{ fontSize: 12, color: "#64748b", alignSelf: "center" }}>
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
                  style={{ fontSize: 11, color: "#94a3b8", cursor: "pointer", userSelect: "none" }}
                >
                  {t("results.howToFix")}
                </summary>
                <p style={{ fontSize: 12, color: "#cbd5e1", marginTop: 4, lineHeight: 1.5 }}>
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
      <p style={{ fontSize: 12, color: "#475569", textAlign: "center", marginTop: 8 }}>
        {t("results.projectId")}{" "}
        <span style={{ fontFamily: "monospace", color: "#64748b" }}>
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
  const { result } = useStore();
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
      <div style={{ flexShrink: 0, borderBottom: "1px solid #1e2330", background: "#0b0e16" }}>
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
                color: "#475569",
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
                  {t(q.labelKey)} {q.score}
                </span>
              );
            })()}
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "#475569",
              fontSize: 20,
              lineHeight: 1,
              padding: "0 2px",
              transition: "color 0.15s",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "#94a3b8")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "#475569")}
            title={t("results.closePanel")}
          >
            ×
          </button>
        </div>
        {/* Tabs */}
        <div style={{ display: "flex", padding: "6px 16px 0" }}>
          {tabs.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              style={{
                background: "none",
                border: "none",
                borderBottom: tab === id ? "2px solid #6366f1" : "2px solid transparent",
                color: tab === id ? "#e2e8f0" : "#64748b",
                fontSize: 12,
                fontWeight: 600,
                letterSpacing: "0.04em",
                padding: "6px 14px",
                cursor: "pointer",
                transition: "color 0.15s",
              }}
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
            <Accordion title={t("results.geoClimate")} defaultOpen>
              <GeoCard />
            </Accordion>
            <Accordion title={t("results.costEstimate")} defaultOpen>
              <CostCard />
            </Accordion>
            <Accordion
              title={t("results.compliance", { count: result.compliance_issues.length })}
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
