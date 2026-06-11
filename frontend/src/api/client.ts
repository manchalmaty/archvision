import axios from "axios";
import type { BuildingParams, GenerationResult } from "../types";

const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
  // Generation runs geoclimate + layout + MEP routing + IFC export — give it room.
  timeout: 120_000,
});

const MAX_RETRIES = 2;

/**
 * Generate a plan with cancellation support and automatic retry.
 * Retries only transient network failures (no HTTP response received);
 * HTTP errors and user cancellation are surfaced immediately.
 */
export async function generatePlan(
  params: BuildingParams,
  signal?: AbortSignal
): Promise<GenerationResult> {
  let lastError: unknown;
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      const { data } = await api.post<GenerationResult>("/generate-plan", params, { signal });
      return data;
    } catch (e) {
      lastError = e;
      const transient = axios.isAxiosError(e) && !e.response && !axios.isCancel(e);
      if (!transient || signal?.aborted || attempt === MAX_RETRIES) throw e;
      // Linear backoff: 1s, 2s.
      await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
    }
  }
  throw lastError;
}

export function isCancelError(e: unknown): boolean {
  return axios.isCancel(e);
}

export function ifcDownloadUrl(projectId: string): string {
  return `/api/v1/download/${projectId}`;
}

export function pdfReportUrl(projectId: string, lang?: string): string {
  return `/api/v1/report/${projectId}?lang=${lang || "en"}`;
}

/** Extract a human-readable message from an unknown error (axios or otherwise). */
export function getErrorMessage(e: unknown, fallback = "Request failed"): string {
  if (axios.isAxiosError(e)) {
    return e.response?.data?.detail || e.message || fallback;
  }
  if (e instanceof Error) return e.message || fallback;
  return fallback;
}
