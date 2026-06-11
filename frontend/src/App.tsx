import { useState, useEffect } from "react";
import { ParameterForm } from "./components/ParameterForm";
import { ThreeViewer } from "./components/ThreeViewer";
import { ResultsPanel } from "./components/ResultsPanel";
import { useStore } from "./store/useStore";
import { generatePlan, getErrorMessage } from "./api/client";
import toast from "react-hot-toast";

export default function App() {
  const { params, setResult, setGenerating, isGenerating, result } = useStore();
  const [rightOpen, setRightOpen] = useState(false);

  useEffect(() => {
    if (result) setRightOpen(true);
  }, [result]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const r = await generatePlan(params);
      setResult(r);
      toast.success("Plan generated successfully!");
    } catch (e) {
      toast.error(getErrorMessage(e, "Generation failed"));
    } finally {
      setGenerating(false);
    }
  };

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
            <p className="text-xs text-slate-500">Architectural Draft Generator</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
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
                    ["1", "Add rooms in the left panel"],
                    ["2", "Press Generate Plan"],
                    ["3", "Explore the 2D plan, 3D model and analysis"],
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
                <p className="text-sm text-slate-400">Generating architectural plan…</p>
                <p className="text-xs text-slate-600 mt-1">Running geoclimate + MEP routing</p>
              </div>
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
              Show Results →
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
        <p className="text-xs text-slate-600">
          Эскизный проект для предварительной оценки. Требует заверения лицензированным
          архитектором. | Schematic design for preliminary assessment. Requires certification by a
          licensed architect.
        </p>
      </footer>
    </div>
  );
}
