import axios from "axios";
import type { BuildingParams, GenerationResult } from "../types";

const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
});

export async function generatePlan(params: BuildingParams): Promise<GenerationResult> {
  const { data } = await api.post<GenerationResult>("/generate-plan", params);
  return data;
}

export function ifcDownloadUrl(projectId: string): string {
  return `/api/v1/download/${projectId}`;
}

/** Extract a human-readable message from an unknown error (axios or otherwise). */
export function getErrorMessage(e: unknown, fallback = "Request failed"): string {
  if (axios.isAxiosError(e)) {
    return e.response?.data?.detail || e.message || fallback;
  }
  if (e instanceof Error) return e.message || fallback;
  return fallback;
}
