import axios from "axios";
import type { BuildingParams, GenerationResult, ProjectSummary } from "../types";

const DEVICE_KEY = "archvision_device_v1";

let sessionToken: string | undefined;

/**
 * Anonymous device identity (no accounts in the MVP): a uuid minted once per
 * browser. The backend stamps it into stored results so /projects lists only
 * this device's history. Private mode / blocked storage → per-session token.
 */
export function deviceToken(): string {
  try {
    let token = localStorage.getItem(DEVICE_KEY);
    if (!token) {
      token = crypto.randomUUID();
      localStorage.setItem(DEVICE_KEY, token);
    }
    return token;
  } catch {
    return (sessionToken ??= crypto.randomUUID());
  }
}

const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
  // Generation runs geoclimate + layout + MEP routing + IFC export — give it room.
  timeout: 120_000,
});

api.interceptors.request.use((config) => {
  config.headers["X-Device-Token"] = deviceToken();
  return config;
});

const MAX_RETRIES = 2;

/** Sleep that rejects immediately when the signal aborts, so Cancel is instant. */
function abortableSleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abortError = () => new DOMException("Aborted", "AbortError");
    if (signal?.aborted) return reject(abortError());
    const onAbort = () => {
      clearTimeout(id);
      reject(abortError());
    };
    const id = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * Generate a plan with cancellation support and automatic retry.
 * Retries only transient network failures (connection never established).
 * Timeouts (ECONNABORTED) are NOT retried — the server is likely still
 * working or overloaded, and re-firing a 120s request multiplies the load.
 */
export async function generatePlan(
  params: BuildingParams,
  signal?: AbortSignal
): Promise<GenerationResult> {
  for (let attempt = 0; ; attempt++) {
    try {
      const { data } = await api.post<GenerationResult>("/generate-plan", params, { signal });
      return data;
    } catch (e) {
      const transient =
        axios.isAxiosError(e) && !e.response && !isCancelError(e) && e.code !== "ECONNABORTED";
      if (!transient || attempt >= MAX_RETRIES) throw e;
      // Linear backoff: 1s, 2s — interruptible by Cancel.
      await abortableSleep(1000 * (attempt + 1), signal);
    }
  }
}

export function isCancelError(e: unknown): boolean {
  return axios.isCancel(e) || (e instanceof DOMException && e.name === "AbortError");
}

export function isRateLimitError(e: unknown): boolean {
  return axios.isAxiosError(e) && e.response?.status === 429;
}

/** This device's recent projects (newest first). */
export async function fetchProjects(): Promise<ProjectSummary[]> {
  const { data } = await api.get<ProjectSummary[]>("/projects");
  return data;
}

/** Full stored result — powers share-by-link and history loading. */
export async function fetchProject(projectId: string): Promise<GenerationResult> {
  const { data } = await api.get<GenerationResult>(`/projects/${projectId}`);
  return data;
}

/** Shareable URL for a generated plan (hash routing, no server round-trip). */
export function shareUrl(projectId: string): string {
  return `${location.origin}${location.pathname}#/p/${projectId}`;
}

export function ifcDownloadUrl(projectId: string): string {
  return `/api/v1/download/${projectId}`;
}

const PDF_LANGS = new Set(["en", "ru", "kk"]);

export function pdfReportUrl(projectId: string, lang?: string): string {
  // Normalize BCP-47 tags ("en-US" → "en") and guard against values the
  // backend's ^(en|ru|kk)$ validator would reject with a 422.
  const base = (lang || "en").split("-")[0];
  return `/api/v1/report/${projectId}?lang=${PDF_LANGS.has(base) ? base : "en"}`;
}

export function dxfExportUrl(projectId: string, lang?: string): string {
  const base = (lang || "en").split("-")[0];
  return `/api/v1/dxf/${projectId}?lang=${PDF_LANGS.has(base) ? base : "en"}`;
}

/** Extract a human-readable message from an unknown error (axios or otherwise). */
export function getErrorMessage(e: unknown, fallback = "Request failed"): string {
  if (axios.isAxiosError(e)) {
    return e.response?.data?.detail || e.message || fallback;
  }
  if (e instanceof Error) return e.message || fallback;
  return fallback;
}
