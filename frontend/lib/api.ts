// API client + shared types mirroring the backend Pydantic schemas.

// Empty default → calls are same-origin ("/api/...") and go through the Next.js rewrite proxy
// (see next.config.mjs) to the backend. Set NEXT_PUBLIC_API_BASE to override with an absolute URL.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export type SignalStatus = "observed" | "predicted";
export type Priority = "P0" | "P1" | "P2" | "P3";
export type Effort = "low" | "medium" | "high";

export interface EngineReadiness {
  engine: string;
  score: number;
  status: SignalStatus;
  rationale: string;
}

export type ChangeType = "content" | "technical";

export interface ConcreteChange {
  change_type: ChangeType;
  target: string;
  original_text: string | null;
  proposed_text: string | null;
  code_language: string | null;
  code_snippet: string | null;
  instructions: string[];
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
  change?: ConcreteChange | null;
}

export interface Alignment {
  goal_alignment_score: number;
  goal_alignment_summary: string;
  query_coverage_score: number;
  query_coverage_summary: string;
  gaps: string[];
}

export type KBCoverageStatus = "covered" | "partial" | "gap";

export interface KBCoverageItem {
  factor: string;
  status: KBCoverageStatus;
  assessment: string;
  related_rec_ids: string[];
}

export type ClaimFlag = "green" | "yellow" | "red";

export interface Claim {
  text: string;
  flag: ClaimFlag;
  claim_type: string;
  rationale: string;
  required_evidence: string[];
  compliant_rewrite: string;
  anchor_id?: string | null;
}

export interface PageSignals {
  final_url: string;
  title: string | null;
  meta_description: string | null;
  canonical: string | null;
  lang: string | null;
  headings: string[]; // e.g. "h1: Title"
  word_count: number;
  has_jsonld: boolean;
  schema_types: string[];
  has_author: boolean;
  published_date: string | null;
  modified_date: string | null;
  robots_txt_present: boolean;
  llms_txt_present: boolean;
  blocks_ai_crawlers: boolean;
  js_dependent: boolean;
}

export interface AnalysisResult {
  executive_summary: string;
  overall_score: number;
  engine_readiness: EngineReadiness[];
  alignment: Alignment;
  recommendations: Recommendation[];
  kb_coverage: KBCoverageItem[];
  claims: Claim[];
  compliance_score: number;
  url: string;
  queries: string[];
  mode: string;
  model_key: string;
  target_engines: string[];
  page_signals: PageSignals | null;
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

// ----------------------------------------------------------------- AI Studio
export interface ProposedFlag {
  quote: string;
  flag: ClaimFlag;
  note: string;
}

export interface RewriteBlock {
  id: string;
  kind: string;
  label: string;
  original: string;
  proposed: string;
  options: string[];
  selected_option_index: number;
  flags: ProposedFlag[];
  changed: boolean;
  is_technical: boolean;
  change_explanation: string | null;
  anchor_id?: string | null;
}

export interface PageRewrite {
  run_id: string;
  summary: string;
  content_blocks: RewriteBlock[];
  technical_blocks: RewriteBlock[];
  model_key: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface StudioState {
  rewrite: PageRewrite | null;
  chat_history: ChatMessage[];
  extra_recommendations: Recommendation[];
}

export interface ChatTurnResult {
  reply: string;
  rewrite: PageRewrite | null;
  edited_block_ids: string[];
  new_recommendations: Recommendation[];
}

export interface PageSnapshot {
  html: string;
  final_url: string;
}

export async function fetchSnapshot(runId: string): Promise<PageSnapshot> {
  const r = await fetch(`${API_BASE}/api/runs/${runId}/snapshot`, { cache: "no-store" });
  if (!r.ok) throw new Error(`Failed to load snapshot (${r.status})`);
  return r.json();
}

export async function getStudio(runId: string): Promise<StudioState> {
  const r = await fetch(`${API_BASE}/api/runs/${runId}/studio`, { cache: "no-store" });
  if (!r.ok) throw new Error(`Failed to load studio (${r.status})`);
  return r.json();
}

export async function generateRewrite(
  runId: string,
  regenerate = false
): Promise<PageRewrite> {
  const r = await fetch(
    `${API_BASE}/api/runs/${runId}/rewrite?regenerate=${regenerate}`,
    { method: "POST" }
  );
  if (!r.ok) throw new Error(`Failed to generate rewrite (${r.status})`);
  return r.json();
}

export async function sendChat(
  runId: string,
  opts: { message: string; blockId?: string | null; file?: File | null }
): Promise<ChatTurnResult> {
  const form = new FormData();
  form.append("message", opts.message);
  if (opts.blockId) form.append("block_id", opts.blockId);
  if (opts.file) form.append("attachment", opts.file);
  const r = await fetch(`${API_BASE}/api/runs/${runId}/chat`, { method: "POST", body: form });
  if (!r.ok) throw new Error(`Chat failed (${r.status})`);
  return r.json();
}

export async function selectOption(
  runId: string,
  blockId: string,
  index: number
): Promise<PageRewrite> {
  const r = await fetch(`${API_BASE}/api/runs/${runId}/select-option`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ block_id: blockId, index }),
  });
  if (!r.ok) throw new Error(`Select option failed (${r.status})`);
  return r.json();
}
