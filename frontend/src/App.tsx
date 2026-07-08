import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ParameterForm } from "./components/ParameterForm";
import { ResultsPanel } from "./components/ResultsPanel";
import { HistoryMenu } from "./components/HistoryMenu";
import { useStore } from "./store/useStore";
import {
  fetchProject,
  generatePlan,
  getErrorMessage,
  isCancelError,
  isRateLimitError,
} from "./api/client";
import { LANGUAGES } from "./i18n";
import toast from "react-hot-toast";

// three.js is ~2/3 of the bundle; splitting the viewer keeps the form
// interactive on first paint while the workspace chunk streams in.
const ThreeViewer = lazy(() =>
  import("./components/ThreeViewer").then((m) => ({ default: m.ThreeViewer }))
);

// Module-scope so StrictMode's double-mounted effect shares one in-flight
// share-load instead of fetching (and setResult-ing) the same project twice.
let shareLoadInFlight: string | null = null;

export default function App() {
  const { t, i18n } = useTranslation();
  const {
    params,
    setResult,
    setGenerating,
    isGenerating,
    result,
    resultStale,
    error,
    setError,
    clearProject,
  } = useStore();
  // Panel-open lives in the store so the 2D viewer can offset its zoom widget.
  const rightOpen = useStore((s) => s.rightPanelOpen);
  const setRightOpen = useStore((s) => s.setRightPanelOpen);
  const abortRef = useRef<AbortController | null>(null);
  // Mobile-only: the parameter form lives in a slide-in drawer below md.
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    if (result) setRightOpen(true);
  }, [result, setRightOpen]);

  // Hash routing: #/p/{id} loads a stored project (share links + refresh
  // restore). Generating sets the hash, so the guard against re-fetching the
  // plan we already show keeps that self-inflicted hashchange a no-op.
  useEffect(() => {
    const load = async () => {
      const m = location.hash.match(/^#\/p\/([0-9a-fA-F-]{36})$/);
      if (!m) return;
      const id = m[1];
      const { result } = useStore.getState();
      if (result?.project_id === id || shareLoadInFlight === id) return;
      shareLoadInFlight = id;
      try {
        const r = await fetchProject(id);
        if (useStore.getState().result?.project_id !== id) useStore.getState().setResult(r);
      } catch (e) {
        useStore.getState().setError(getErrorMessage(e, t("app.shareLoadFailed")));
      } finally {
        shareLoadInFlight = null;
      }
    };
    load();
    window.addEventListener("hashchange", load);
    return () => window.removeEventListener("hashchange", load);
  }, [t]);

  const handleGenerate = async () => {
    abortRef.current = new AbortController();
    setDrawerOpen(false); // reveal the canvas on mobile while it generates
    setGenerating(true);
    setError(null);
    try {
      const r = await generatePlan(params, abortRef.current.signal);
      setResult(r);
      // Make the URL shareable + refresh-proof for the plan on screen.
      location.hash = `/p/${r.project_id}`;
      toast.success(t("app.genSuccess"));
    } catch (e) {
      if (isCancelError(e)) {
        toast(t("app.cancelled"));
      } else if (isRateLimitError(e)) {
        setError(t("app.rateLimited"));
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

  // Fresh start: F5 deliberately restores the plan via the #/p/{id} hash, so
  // "new project" must drop both the state AND the hash or reload resurrects it.
  const handleNewProject = () => {
    clearProject();
    history.replaceState(null, "", location.pathname + location.search);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden" }}>
      {/* Header */}
      <header className="border-b border-surface-border px-3 sm:px-6 py-3 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Mobile: hamburger opens the parameter drawer */}
          <button
            onClick={() => setDrawerOpen(true)}
            aria-label={t("app.openParams")}
            className="md:hidden w-9 h-9 flex items-center justify-center rounded-lg border border-surface-border text-slate-600 active:bg-surface-panel"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              strokeLinecap="round"
              className="w-5 h-5"
            >
              <path d="M4 7h16M4 12h16M4 17h16" />
            </svg>
          </button>
          {/* Brand mark — the "AV" monogram, white on ArchVision red */}
          <div className="w-9 h-9 rounded-sm bg-brand-500 flex items-center justify-center flex-shrink-0">
            <svg viewBox="0 0 220 140" className="w-6 h-6" fill="#ffffff" aria-hidden="true">
              <path d="M14 120 L30 120 L58 22 L46 22 Z" />
              <path d="M62 22 L74 22 L102 120 L86 120 Z" />
              <rect x="40" y="80" width="42" height="13" />
              <path d="M134 22 L147 22 L176 120 L164 120 Z" />
              <path d="M198 22 L211 22 L190 120 L178 120 Z" />
            </svg>
          </div>
          <div>
            <h1 className="font-display text-[15px] font-bold tracking-tight text-slate-900 leading-none">
              ArchVision<span className="text-brand-500">&nbsp;AI</span>
            </h1>
            <p className="hidden sm:block text-[11px] text-slate-500 mt-0.5">
              {t("app.subtitle")}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {result && (
            <button
              onClick={handleNewProject}
              className="hidden sm:inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-slate-600 border border-surface-border rounded hover:text-slate-800 hover:bg-surface-card transition-colors"
            >
              + {t("app.newProject")}
            </button>
          )}
          <HistoryMenu />
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
          <span className="hidden sm:inline-block text-[10px] font-semibold text-slate-500 border border-surface-border rounded-full px-2 py-px">
            Beta
          </span>
        </div>
      </header>

      {/* Workspace */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden", position: "relative" }}>
        {/* Mobile backdrop behind the drawer */}
        {drawerOpen && (
          <div
            className="fixed inset-0 bg-black/30 z-30 md:hidden"
            onClick={() => setDrawerOpen(false)}
          />
        )}
        {/* Left panel — static 280px column on desktop, slide-in drawer below md */}
        <aside
          className={`fixed inset-y-0 left-0 z-40 w-[300px] max-w-[85vw] transform transition-transform duration-200 shadow-xl
            ${drawerOpen ? "translate-x-0" : "-translate-x-full"}
            md:static md:z-auto md:w-[280px] md:translate-x-0 md:shadow-none md:transform-none
            flex-shrink-0 overflow-y-auto border-r border-surface-border bg-surface-panel px-4 pt-4 pb-0 flex flex-col gap-3`}
        >
          <ParameterForm onGenerate={handleGenerate} />
        </aside>

        {/* Center — always fills remaining space, never shifts */}
        <main className="flex-1 relative bg-surface-dark paper-grid overflow-hidden">
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

        {/* Right panel — overlay column on desktop, bottom sheet below md;
            absolutely positioned so it never shifts the flex layout */}
        {result && rightOpen && (
          <aside
            className="absolute z-10 flex flex-col bg-surface-panel border-surface-border
              max-md:inset-x-0 max-md:bottom-0 max-md:h-[60vh] max-md:rounded-t-2xl max-md:border-t max-md:shadow-2xl
              md:right-0 md:top-0 md:bottom-0 md:w-[320px] md:border-l"
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
