import axios from "axios";
import type { BuildingParams, GenerationResult, ComplianceIssue, MEPConflict } from "../types";

const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
});

export async function generatePlan(params: BuildingParams): Promise<GenerationResult> {
  const { data } = await api.post<GenerationResult>("/generate-plan", params);
  return data;
}

export async function checkCompliance(
  country: string,
  rooms: BuildingParams["rooms"],
  floors: number
): Promise<ComplianceIssue[]> {
  const { data } = await api.post<ComplianceIssue[]>("/compliance-check", {
    country,
    rooms,
    floors,
  });
  return data;
}

export async function routeMEP(
  projectId: string,
  rooms: GenerationResult["rooms"],
  floors: number
): Promise<MEPConflict[]> {
  const { data } = await api.post<MEPConflict[]>("/mep-routing", {
    project_id: projectId,
    rooms,
    floors,
  });
  return data;
}

export function ifcDownloadUrl(projectId: string): string {
  return `/api/v1/download/${projectId}`;
}
