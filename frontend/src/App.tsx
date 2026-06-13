import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { ParameterForm } from "./components/ParameterForm";
import { ThreeViewer } from "./components/ThreeViewer";
import { ResultsPanel } from "./components/ResultsPanel";
import { useStore } from "./store/useStore";
import { generatePlan, getErrorMessage, isCancelError } from "./api/client";
import { LANGUAGES } from "./i18n";
import toast from "react-hot-toast";

export default function App() {
  const { t, i18n } = useTranslation();
  const { params, setResult, setGenerating, isGenerating, result, resultStale, error, setError } =
    useStore();
  const [rightOpen, setRightOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (result) setRightOpen(true);
  }, [result]);

  const handleGenerate = async () => {
    abortRef.current = new AbortController();
    setGenerating(true);
    setError(null);
    try {
      const r = await generatePlan(params, abortRef.current.signal);
      setResult(r);
      toast.success(t("app.genSuccess"));
    } catch (e) {
      if (isCancelError(e)) {
        toast(t("app.cancelled"));
      } else {
        // The persistent banner is the single error surface — no extra toast.
        setError(getErrorMessage(e, t("app.genFailed")));
      }
    } finally {
      setGenerating(false);
      abortRef.current = null;
    }
  };

  const handleCancel = () => abortRef.current?.abort();

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden" }}>
      {/* Header */}
      <header className="border-b border-surface-border px-6 py-3 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          {/* Brand mark — triangular "A" / roof over a blueprint crosshair */}
          <div className="w-9 h-9 rounded-md bg-slate-900 flex items-center justify-center flex-shrink-0">
            <svg viewBox="0 0 32 32" className="w-9 h-9">
              <line
                x1="3"
                y1="11"
                x2="29"
                y2="11"
                stroke="#38bdf8"
                strokeWidth="0.7"
                opacity="0.5"
              />
              <line
                x1="3"
                y1="22"
                x2="29"
                y2="22"
                stroke="#38bdf8"
                strokeWidth="0.7"
                opacity="0.5"
              />
              <line
                x1="16"
                y1="3"
                x2="16"
                y2="29"
                stroke="#38bdf8"
                strokeWidth="0.7"
                opacity="0.5"
              />
              <path
                d="M16 7 L25 25 H7 Z"
                fill="none"
                stroke="#ffffff"
                strokeWidth="2.2"
                strokeLinejoin="round"
              />
              <line x1="12" y1="19.5" x2="20" y2="19.5" stroke="#38bdf8" strokeWidth="2.2" />
            </svg>
          </div>
          <div>
            <h1 className="font-display text-lg font-bold tracking-tight text-slate-900 leading-none">
              ArchVision
              <span
                style={{
                  backgroundImage: "linear-gradient(135deg, #2dd4bf 0%, #1e3a8a 100%)",
                  WebkitBackgroundClip: "text",
                  backgroundClip: "text",
                  color: "transparent",
                }}
              >
                &nbsp;AI
              </span>
            </h1>
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-500 mt-0.5">
              {t("app.subtitle")}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Language switcher */}
          <div className="flex bg-surface-card border border-surface-border rounded-lg p-0.5">
            {LANGUAGES.map(({ code, label }) => (
              <button
                key={code}
                onClick={() => i18n.changeLanguage(code)}
                className={`px-2 py-1 text-xs font-semibold rounded-md transition-all ${
                  i18n.resolvedLanguage === code
                    ? "bg-brand-600 text-white"
                    : "text-slate-500 hover:text-slate-800"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <span className="text-xs text-slate-500 border border-surface-border rounded px-2 py-1">
            Beta
          </span>
        </div>
      </header>

      {/* Workspace */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden", position: "relative" }}>
        {/* Left panel — fixed 280px, never moves */}
        <aside
          style={{
            width: 280,
            flexShrink: 0,
            overflowY: "auto",
            borderRight: "1px solid #e2e8f0",
            padding: "16px 16px 0",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
            background: "#f1f5f9",
          }}
        >
          <ParameterForm onGenerate={handleGenerate} />
        </aside>

        {/* Center — always fills remaining space, never shifts */}
        <main style={{ flex: 1, position: "relative", background: "#f8fafc", overflow: "hidden" }}>
          <ThreeViewer />
          {!result && !isGenerating && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-center text-slate-600 max-w-xs">
                <svg
                  viewBox="0 0 24 24"
                  className="w-14 h-14 mx-auto mb-4 opacity-20"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={1}
                >
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <path d="M3 9h18M9 21V9" />
                </svg>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {[
                    ["1", t("app.step1")],
                    ["2", t("app.step2")],
                    ["3", t("app.step3")],
                  ].map(([n, text]) => (
                    <div
                      key={n}
                      style={{ display: "flex", alignItems: "center", gap: 10, color: "#9ca3af" }}
                    >
                      <span
                        style={{
                          width: 22,
                          height: 22,
                          borderRadius: "50%",
                          border: "1px solid #cbd5e1",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 11,
                          fontWeight: 700,
                          flexShrink: 0,
                        }}
                      >
                        {n}
                      </span>
                      <span style={{ fontSize: 13, textAlign: "left" }}>{text}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
          {isGenerating && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/70 backdrop-blur-sm">
              <div className="text-center">
                <div className="w-12 h-12 border-2 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <p className="text-sm text-slate-400">{t("app.generating")}</p>
                <p className="text-xs text-slate-600 mt-1">{t("app.generatingSub")}</p>
                <button
                  onClick={handleCancel}
                  style={{
                    marginTop: 16,
                    background: "transparent",
                    border: "1px solid #cbd5e1",
                    borderRadius: 8,
                    color: "#4b5563",
                    fontSize: 13,
                    fontWeight: 600,
                    padding: "7px 18px",
                    cursor: "pointer",
                  }}
                >
                  {t("app.cancel")}
                </button>
              </div>
            </div>
          )}
          {/* Notices: error banner + stale-params hint, stacked top-center */}
          {!isGenerating && (error || (result && resultStale)) && (
            <div
              style={{
                position: "absolute",
                top: 56,
                left: "50%",
                transform: "translateX(-50%)",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 8,
                zIndex: 6,
                maxWidth: 420,
              }}
            >
              {error && (
                <div
                  style={{
                    background: "#fef2f2",
                    border: "1px solid #fecaca",
                    borderRadius: 8,
                    boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
                    padding: "10px 14px",
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 10,
                  }}
                >
                  <span style={{ fontSize: 13, color: "#b91c1c", lineHeight: 1.4 }}>{error}</span>
                  <button
                    onClick={() => setError(null)}
                    aria-label={t("app.dismissError")}
                    style={{
                      background: "none",
                      border: "none",
                      color: "#dc2626",
                      cursor: "pointer",
                      fontSize: 16,
                      lineHeight: 1,
                      padding: 0,
                    }}
                  >
                    ×
                  </button>
                </div>
              )}
              {result && resultStale && (
                <div
                  style={{
                    background: "#fffbeb",
                    border: "1px solid #fcd34d",
                    borderRadius: 20,
                    boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
                    padding: "5px 14px",
                    fontSize: 12,
                    color: "#b45309",
                  }}
                >
                  {t("app.staleParams")}
                </div>
              )}
            </div>
          )}
          {/* Toggle button when panel is closed after first generation */}
          {result && !rightOpen && (
            <button
              onClick={() => setRightOpen(true)}
              style={{
                position: "absolute",
                bottom: 16,
                right: 16,
                background: "#e2e8f0",
                border: "1px solid #cbd5e1",
                borderRadius: 8,
                color: "#4b5563",
                fontSize: 12,
                fontWeight: 600,
                padding: "6px 12px",
                cursor: "pointer",
                zIndex: 5,
              }}
            >
              {t("app.showResults")}
            </button>
          )}
        </main>

        {/* Right panel — absolutely positioned, overlays center, does NOT shift flex layout */}
        {result && rightOpen && (
          <aside
            style={{
              position: "absolute",
              right: 0,
              top: 0,
              bottom: 0,
              width: 320,
              background: "#f1f5f9",
              borderLeft: "1px solid #e2e8f0",
              zIndex: 10,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <ResultsPanel onClose={() => setRightOpen(false)} />
          </aside>
        )}
      </div>

      {/* Footer */}
      <footer className="border-t border-surface-border px-6 py-2 text-center flex-shrink-0">
        <p className="text-xs text-slate-600">{t("app.disclaimer")}</p>
      </footer>
    </div>
  );
}
