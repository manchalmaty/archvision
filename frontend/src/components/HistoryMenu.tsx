import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchProject, fetchProjects, getErrorMessage } from "../api/client";
import { useStore } from "../store/useStore";
import type { ProjectSummary } from "../types";

/** Header dropdown listing this device's past generations (server-side history). */
export function HistoryMenu() {
  const { t, i18n } = useTranslation();
  const setResult = useStore((s) => s.setResult);
  const setError = useStore((s) => s.setError);
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<ProjectSummary[] | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    fetchProjects()
      .then((list) => alive && setEntries(list))
      .catch(() => alive && setEntries([]));
    const onDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("pointerdown", onDown);
    return () => {
      alive = false;
      window.removeEventListener("pointerdown", onDown);
    };
  }, [open]);

  const load = async (id: string) => {
    setOpen(false);
    try {
      const r = await fetchProject(id);
      setResult(r);
      location.hash = `/p/${id}`;
    } catch (e) {
      setError(getErrorMessage(e, t("history.loadFailed")));
    }
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        title={t("history.title")}
        className={`flex items-center gap-1.5 px-2 py-1.5 text-xs font-semibold rounded-lg border transition-colors ${
          open
            ? "bg-surface-card border-slate-300 text-slate-800"
            : "bg-surface-card border-surface-border text-slate-500 hover:text-slate-800 hover:border-slate-300"
        }`}
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          className="w-3.5 h-3.5"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 3" />
        </svg>
        <span className="hidden sm:inline">{t("history.title")}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1.5 w-72 max-h-80 overflow-y-auto rounded-xl border border-surface-border bg-surface-card shadow-lg z-30 p-1.5">
          {entries === null && <p className="px-3 py-4 text-xs text-slate-500 text-center">…</p>}
          {entries?.length === 0 && (
            <p className="px-3 py-4 text-xs text-slate-500 text-center">{t("history.empty")}</p>
          )}
          {entries?.map((e) => (
            <button
              key={e.project_id}
              onClick={() => load(e.project_id)}
              className="w-full flex items-center justify-between gap-2 px-2.5 py-2 rounded-lg text-left hover:bg-surface-panel transition-colors"
            >
              <span className="min-w-0">
                <span className="block text-xs font-semibold text-slate-700 whitespace-nowrap">
                  {t("presets.roomsSummary", { count: e.rooms, area: e.total_area_m2.toFixed(0) })}
                </span>
                <span className="block text-[10px] text-slate-500 mt-0.5">
                  {new Date(e.created_at).toLocaleString(i18n.language, {
                    day: "numeric",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                  {" · "}
                  {t("history.floors", { count: e.floors })}
                </span>
              </span>
              <span className="font-mono text-[10px] text-slate-400 flex-shrink-0">
                {e.project_id.slice(0, 8)}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
