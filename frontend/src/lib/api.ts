/**
 * src/lib/api.ts
 * Type-safe API client covering all backend FastAPI endpoints.
 */

import { components, paths } from "./api-types";

export type Schemas = components["schemas"];
export type DocumentInfo = Schemas["DocumentInfo"];
export type DocumentTextResponse = Schemas["DocumentTextResponse"];
export type LineIndexResponse = Schemas["LineIndexResponse"];
export type SectionEntry = Schemas["SectionEntry"];
export type SearchMatch = Schemas["SearchMatch"];
export type QuestionSchema = Schemas["QuestionSchema"];
export type QuestionCreateSchema = Schemas["QuestionCreateSchema"];
export type QuestionUpdateSchema = Schemas["QuestionUpdateSchema"];
export type QuestionReviewRequest = Schemas["QuestionReviewRequest"];
export type QuestionStats = Schemas["QuestionStats"];
export type ValidationResult = Schemas["ValidationResult"];
export type PresetInfo = Schemas["PresetInfo"];
export type ModelInfo = Schemas["ModelInfo"];
export type ChunkerInfo = Schemas["ChunkerInfo"];
export type EstimateRequest = Schemas["EstimateRequest"];
export type EstimateResponse = Schemas["EstimateResponse"];
export type ExperimentCreateRequest = Schemas["ExperimentCreateRequest"];
export type ExperimentResponse = Schemas["ExperimentResponse"];
export type LeaderboardRow = Schemas["LeaderboardRow"];
export type HeatmapData = Schemas["HeatmapData"];
export type ParetoPoint = Schemas["ParetoPoint"];
export type QuestionDrilldown = Schemas["QuestionDrilldown"];
export type CompareRequest = Schemas["CompareRequest"];
export type CompareResponse = Schemas["CompareResponse"];
export type PlaygroundQueryRequest = Schemas["PlaygroundQueryRequest"];
export type MultiPlaygroundResponse = Schemas["MultiPlaygroundResponse"];
export type SinglePlaygroundResponse = Schemas["SinglePlaygroundResponse"];
export type DecisionMatrixWeights = Schemas["DecisionMatrixWeights"];
export type DecisionMatrixResponse = Schemas["DecisionMatrixResponse"];
export type SettingsSchema = Schemas["SettingsSchema"];

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    let errorDetail = `Request failed: ${res.status} ${res.statusText}`;
    try {
      const errJson = await res.json();
      if (errJson.error && errJson.error.message) {
        errorDetail = errJson.error.message;
      } else if (errJson.detail) {
        errorDetail = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // Keep default error text
    }
    throw new Error(errorDetail);
  }

  return res.json() as Promise<T>;
}

export const api = {
  // Health
  getHealth: () => fetchJson<{ status: string; models: string[]; docs: string[]; questions_count: number }>("/api/health"),

  // Corpus
  listDocuments: () => fetchJson<DocumentInfo[]>("/api/corpus/documents"),
  getDocumentText: (docId: string, start?: number, end?: number) => {
    const params = new URLSearchParams();
    if (start !== undefined) params.append("start", start.toString());
    if (end !== undefined) params.append("end", end.toString());
    const query = params.toString() ? `?${params.toString()}` : "";
    return fetchJson<DocumentTextResponse>(`/api/corpus/documents/${docId}/text${query}`);
  },
  getDocumentLineIndex: (docId: string) =>
    fetchJson<LineIndexResponse>(`/api/corpus/documents/${docId}/line-index`),
  getDocumentSections: (docId: string) =>
    fetchJson<SectionEntry[]>(`/api/corpus/documents/${docId}/sections`),
  searchCorpus: (q: string, docId?: string, limit = 20) => {
    const params = new URLSearchParams({ q, limit: limit.toString() });
    if (docId) params.append("doc_id", docId);
    return fetchJson<SearchMatch[]>(`/api/corpus/search?${params.toString()}`);
  },

  // Questions
  listQuestions: (params?: { doc_id?: string; verified?: boolean; type?: string; difficulty?: string }) => {
    const urlParams = new URLSearchParams();
    if (params?.doc_id) urlParams.append("doc_id", params.doc_id);
    if (params?.verified !== undefined) urlParams.append("verified", params.verified.toString());
    if (params?.type) urlParams.append("type", params.type);
    if (params?.difficulty) urlParams.append("difficulty", params.difficulty);
    const qs = urlParams.toString() ? `?${urlParams.toString()}` : "";
    return fetchJson<QuestionSchema[]>(`/api/questions${qs}`);
  },
  getQuestion: (id: string) => fetchJson<QuestionSchema>(`/api/questions/${id}`),
  createQuestion: (data: QuestionCreateSchema) =>
    fetchJson<QuestionSchema>("/api/questions", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateQuestion: (id: string, data: QuestionUpdateSchema) =>
    fetchJson<QuestionSchema>(`/api/questions/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteQuestion: (id: string) =>
    fetchJson<{ message: string }>(`/api/questions/${id}`, { method: "DELETE" }),
  reviewQuestion: (id: string, data: QuestionReviewRequest) =>
    fetchJson<{ status: string; question?: QuestionSchema; message?: string }>(
      `/api/questions/${id}/review`,
      { method: "POST", body: JSON.stringify(data) }
    ),
  getQuestionStats: () => fetchJson<QuestionStats>("/api/questions/stats"),
  getReviewProgress: () => fetchJson<{ total: number; verified: number; unverified: number; percent_complete: number }>("/api/questions/review/progress"),
  getNextUnverifiedQuestion: () => fetchJson<QuestionSchema | null>("/api/questions/review/next"),
  validateQuestions: () => fetchJson<ValidationResult>("/api/questions/validate", { method: "POST" }),
  exportQuestionsCsvUrl: () => "/api/questions/export",
  importQuestionsCsv: async (file: File) => {
    const text = await file.text();
    const res = await fetch("/api/questions/import", {
      method: "POST",
      headers: { "Content-Type": "text/csv" },
      body: text,
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // Configs
  getPresets: () => fetchJson<PresetInfo[]>("/api/configs/presets"),
  getModels: () => fetchJson<ModelInfo[]>("/api/configs/models"),
  getChunkers: () => fetchJson<ChunkerInfo[]>("/api/configs/chunkers"),
  estimateExperiment: (req: EstimateRequest) =>
    fetchJson<EstimateResponse>("/api/configs/estimate", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  // Experiments
  listExperiments: () => fetchJson<ExperimentResponse[]>("/api/experiments"),
  getExperiment: (id: string) => fetchJson<ExperimentResponse>(`/api/experiments/${id}`),
  createExperiment: (req: ExperimentCreateRequest) =>
    fetchJson<ExperimentResponse>("/api/experiments", {
      method: "POST",
      body: JSON.stringify(req),
    }),
  cancelExperiment: (id: string) =>
    fetchJson<{ message: string }>(`/api/experiments/${id}/cancel`, { method: "POST" }),
  resumeExperiment: (id: string) =>
    fetchJson<ExperimentResponse>(`/api/experiments/${id}/resume`, { method: "POST" }),
  deleteExperiment: (id: string) =>
    fetchJson<{ message: string }>(`/api/experiments/${id}`, { method: "DELETE" }),
  getExperimentLogs: (id: string, tail = 100) =>
    fetchJson<{ experiment_id: string; lines: string[] }>(`/api/experiments/${id}/log?tail=${tail}`),

  // Results
  getLeaderboard: (expId: string) =>
    fetchJson<{ experiment_id: string; unverified_included: boolean; verified_questions_count: number; unverified_questions_count: number; rows: LeaderboardRow[] }>(
      `/api/results/${expId}/leaderboard`
    ),
  getHeatmap: (expId: string, metric = "hit_rate") =>
    fetchJson<HeatmapData>(`/api/results/${expId}/heatmap?metric=${metric}`),
  getPareto: (expId: string) =>
    fetchJson<{ experiment_id: string; points: ParetoPoint[]; frontier_points: ParetoPoint[] }>(
      `/api/results/${expId}/pareto`
    ),
  getQuestionDrilldown: (expId: string, qid: string) =>
    fetchJson<QuestionDrilldown>(`/api/results/${expId}/drilldown/${qid}`),

  // Compare
  compareRuns: (req: CompareRequest) =>
    fetchJson<CompareResponse>("/api/compare", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  // Playground
  queryPlayground: (req: PlaygroundQueryRequest) =>
    fetchJson<MultiPlaygroundResponse | SinglePlaygroundResponse>("/api/playground/query", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  // Decision Matrix
  getDecisionMatrixPresets: () =>
    fetchJson<Record<string, DecisionMatrixWeights>>("/api/decision-matrix/presets"),
  computeDecisionMatrix: (weights: DecisionMatrixWeights, expId?: string) => {
    const url = expId ? `/api/decision-matrix?experiment_id=${expId}` : "/api/decision-matrix";
    return fetchJson<DecisionMatrixResponse>(url, {
      method: "POST",
      body: JSON.stringify(weights),
    });
  },

  // Export
  exportCsvUrl: (expId: string) => `/api/export/csv?experiment_id=${expId}`,
  exportMarkdownUrl: (expId: string) => `/api/export/markdown?experiment_id=${expId}`,
  exportLatexUrl: (expId: string) => `/api/export/latex?experiment_id=${expId}`,
  getManifest: (expId: string) => fetchJson<Record<string, unknown>>(`/api/export/manifest?experiment_id=${expId}`),
  getMethodology: (expId: string) =>
    fetchJson<{ experiment_id: string; methodology_markdown: string }>(`/api/export/methodology?experiment_id=${expId}`),

  // Settings
  getSettings: () => fetchJson<SettingsSchema>("/api/settings"),
  updateSettings: (settings: SettingsSchema) =>
    fetchJson<SettingsSchema>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
  clearCache: (which: "faiss" | "llm" | "all") =>
    fetchJson<{ message: string; which: string }>("/api/settings/clear-cache", {
      method: "POST",
      body: JSON.stringify({ which }),
    }),
};
