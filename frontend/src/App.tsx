import { lazy, Suspense, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { ParameterForm } from "./components/ParameterForm";
import { ResultsPanel } from "./components/ResultsPanel";
import { useStore } from "./store/useStore";
import { generatePlan, getErrorMessage, isCancelError } from "./api/client";
import { LANGUAGES } from "./i18n";
import toast from "react-hot-toast";

// three.js is ~2/3 of the bundle; splitting the viewer keeps the form
// interactive on first paint while the workspace chunk streams in.
const ThreeViewer = lazy(() =>
  import("./components/ThreeViewer").then((m) => ({ default: m.ThreeViewer }))
);

export default function App() {
  const { t, i18n } = useTranslation();
  const { params, setResult, setGenerating, isGenerating, result, resultStale, error, setError } =
    useStore();
  // Panel-open lives in the store so the 2D viewer can offset its zoom widget.
  const rightOpen = useStore((s) => s.rightPanelOpen);
  const setRightOpen = useStore((s) => s.setRightPanelOpen);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (result) setRightOpen(true);
  }, [result, setRightOpen]);

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
          {/* Brand mark — the "AV" monogram, white on ArchVision red */}
          <div className="w-9 h-9 rounded-md bg-brand-500 flex items-center justify-center flex-shrink-0">
            <svg viewBox="0 0 220 140" className="w-6 h-6" fill="#ffffff" aria-hidden="true">
              <path d="M14 120 L30 120 L58 22 L46 22 Z" />
              <path d="M62 22 L74 22 L102 120 L86 120 Z" />
              <rect x="40" y="80" width="42" height="13" />
              <path d="M134 22 L147 22 L176 120 L164 120 Z" />
              <path d="M198 22 L211 22 L190 120 L178 120 Z" />
            </svg>
          </div>
          <div>
            <h1 className="font-display text-lg font-bold tracking-tight text-slate-900 leading-none">
              ArchVision<span className="text-brand-500">&nbsp;AI</span>
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
        <aside className="w-[280px] flex-shrink-0 overflow-y-auto border-r border-surface-border bg-surface-panel px-4 pt-4 pb-0 flex flex-col gap-3">
          <ParameterForm onGenerate={handleGenerate} />
        </aside>

        {/* Center — always fills remaining space, never shifts */}
        <main className="flex-1 relative bg-surface-dark overflow-hidden">
          <Suspense fallback={null}>
            <ThreeViewer />
          </Suspense>
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
                <div className="bg-red-50 border border-red-200 rounded-lg shadow-sm px-3.5 py-2.5 flex items-start gap-2.5">
                  <span className="text-[13px] text-red-700 leading-snug">{error}</span>
                  <button
                    onClick={() => setError(null)}
                    aria-label={t("app.dismissError")}
                    className="text-red-600 hover:text-red-800 text-base leading-none p-0 transition-colors"
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
              className="absolute bottom-4 right-4 z-[5] bg-surface-border border border-slate-300 rounded-lg text-slate-600 text-xs font-semibold px-3 py-1.5 hover:bg-slate-300 transition-colors"
            >
              {t("app.showResults")}
            </button>
          )}
        </main>

        {/* Right panel — absolutely positioned, overlays center, does NOT shift flex layout */}
        {result && rightOpen && (
          <aside className="absolute right-0 top-0 bottom-0 w-[320px] bg-surface-panel border-l border-surface-border z-10 flex flex-col">
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
