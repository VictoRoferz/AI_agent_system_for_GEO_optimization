// API client + shared types mirroring the backend Pydantic schemas.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8741";

export type SignalStatus = "observed" | "predicted";
export type Priority = "P0" | "P1" | "P2" | "P3";
export type Effort = "low" | "medium" | "high";

export interface EngineReadiness {
  engine: string;
  score: number;
  status: SignalStatus;
  rationale: string;
}

export interface Recommendation {
  id: string;
  title: string;
  description: string;
  why_it_matters: string;
  expected_impact: string;
  impact_score: number;
  effort: Effort;
  confidence: number;
  evidence: string[];
  target_engine: string | null;
  priority: Priority;
  priority_rank: number;
}

export interface Alignment {
  goal_alignment_score: number;
  goal_alignment_summary: string;
  query_coverage_score: number;
  query_coverage_summary: string;
  gaps: string[];
}

export interface AnalysisResult {
  executive_summary: string;
  overall_score: number;
  engine_readiness: EngineReadiness[];
  alignment: Alignment;
  recommendations: Recommendation[];
  url: string;
  queries: string[];
  mode: string;
  model_key: string;
  target_engines: string[];
  notes: string[];
}

export interface Option {
  key: string;
  label: string;
}
export interface ModelOption extends Option {
  provider: string;
  configured: boolean;
}

export interface RunSummary {
  id: string;
  created_at: string;
  url: string;
  mode: string;
  model_key: string;
  status: string;
  overall_score: number | null;
  goals_filename: string | null;
}

export async function getOptions(): Promise<{ modes: Option[]; target_engines: Option[] }> {
  const r = await fetch(`${API_BASE}/api/options`, { cache: "no-store" });
  return r.json();
}

export async function getModels(): Promise<{ default: string; models: ModelOption[] }> {
  const r = await fetch(`${API_BASE}/api/models`, { cache: "no-store" });
  return r.json();
}

export async function listRuns(): Promise<RunSummary[]> {
  const r = await fetch(`${API_BASE}/api/runs`, { cache: "no-store" });
  return r.json();
}

export async function getRun(id: string): Promise<{ result: AnalysisResult | null; status: string; error: string | null }> {
  const r = await fetch(`${API_BASE}/api/runs/${id}`, { cache: "no-store" });
  return r.json();
}

export interface ProgressEvent {
  step: string;
  message: string;
  pct: number;
}

// Stream an analysis: POST multipart, read the text/event-stream response body.
export async function runAnalysis(
  form: FormData,
  handlers: {
    onProgress?: (p: ProgressEvent) => void;
    onResult?: (r: AnalysisResult & { run_id: string }) => void;
    onError?: (msg: string) => void;
    onRun?: (runId: string) => void;
  }
): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/analyze`, { method: "POST", body: form });
  if (!resp.body) throw new Error("No response stream");
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const evMatch = chunk.match(/^event: (.+)$/m);
      const dataMatch = chunk.match(/^data: (.+)$/m);
      if (!evMatch || !dataMatch) continue;
      const event = evMatch[1];
      const data = JSON.parse(dataMatch[1]);
      if (event === "run") handlers.onRun?.(data.run_id);
      else if (event === "progress") handlers.onProgress?.(data);
      else if (event === "result") handlers.onResult?.(data);
      else if (event === "error") handlers.onError?.(data.message);
    }
  }
}

export const PRIORITY_COLOR: Record<Priority, string> = {
  P0: "bg-priority-p0",
  P1: "bg-priority-p1",
  P2: "bg-priority-p2",
  P3: "bg-priority-p3",
};

export function engineLabel(key: string): string {
  return (
    {
      chatgpt: "ChatGPT",
      ai_overviews: "AI Overviews",
      perplexity: "Perplexity",
      gemini: "Gemini",
    }[key] || key
  );
}
