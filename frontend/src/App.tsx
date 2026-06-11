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
  const { params, setResult, setGenerating, isGenerating, result, error, setError } = useStore();
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
        const msg = getErrorMessage(e, t("app.genFailed"));
        setError(msg);
        toast.error(msg);
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
          <div className="w-8 h-8 bg-brand-600 rounded-lg flex items-center justify-center">
            <svg viewBox="0 0 24 24" className="w-5 h-5 text-white fill-current">
              <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
              <polyline points="9 22 9 12 15 12 15 22" />
            </svg>
          </div>
          <div>
            <h1 className="text-lg font-bold text-white">ArchVision AI</h1>
            <p className="text-xs text-slate-500">{t("app.subtitle")}</p>
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
                    : "text-slate-400 hover:text-slate-200"
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
            borderRight: "1px solid #1e2330",
            padding: "16px",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
            background: "#0b0e16",
          }}
        >
          <ParameterForm onGenerate={handleGenerate} />
        </aside>

        {/* Center — always fills remaining space, never shifts */}
        <main style={{ flex: 1, position: "relative", background: "#020617", overflow: "hidden" }}>
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
                      style={{ display: "flex", alignItems: "center", gap: 10, color: "#475569" }}
                    >
                      <span
                        style={{
                          width: 22,
                          height: 22,
                          borderRadius: "50%",
                          border: "1px solid #2a2e3a",
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
            <div className="absolute inset-0 flex items-center justify-center bg-slate-950/80">
              <div className="text-center">
                <div className="w-12 h-12 border-2 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <p className="text-sm text-slate-400">{t("app.generating")}</p>
                <p className="text-xs text-slate-600 mt-1">{t("app.generatingSub")}</p>
                <button
                  onClick={handleCancel}
                  style={{
                    marginTop: 16,
                    background: "transparent",
                    border: "1px solid #2a2e3a",
                    borderRadius: 8,
                    color: "#94a3b8",
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
          {/* Error banner — persists until the next generation attempt */}
          {error && !isGenerating && (
            <div
              style={{
                position: "absolute",
                top: 16,
                left: "50%",
                transform: "translateX(-50%)",
                maxWidth: 420,
                background: "#2d1216",
                border: "1px solid #7f1d1d",
                borderRadius: 8,
                padding: "10px 14px",
                zIndex: 6,
                display: "flex",
                alignItems: "flex-start",
                gap: 10,
              }}
            >
              <span style={{ fontSize: 13, color: "#fca5a5", lineHeight: 1.4 }}>{error}</span>
              <button
                onClick={() => setError(null)}
                aria-label={t("app.dismissError")}
                style={{
                  background: "none",
                  border: "none",
                  color: "#7f1d1d",
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
          {/* Toggle button when panel is closed after first generation */}
          {result && !rightOpen && (
            <button
              onClick={() => setRightOpen(true)}
              style={{
                position: "absolute",
                bottom: 16,
                right: 16,
                background: "#1e2330",
                border: "1px solid #2a2e3a",
                borderRadius: 8,
                color: "#94a3b8",
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
              background: "#0b0e16",
              borderLeft: "1px solid #1e2330",
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
