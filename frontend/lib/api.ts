// API client + shared types mirroring the backend Pydantic schemas.

import { streamPOST } from "./sse";

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
  rationale?: Rationale | null; // structured why (agent runs)
  source_agent?: string | null; // expert id that produced it (agent runs)
  block_ids?: string[]; // rewrite blocks implementing it (agent runs)
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
  factor_id?: string | null;
  related_block_ids?: string[];
}

// ----------------------------------------------------- explainability (agent)
export interface EvidenceRef {
  quote: string;
  anchor_id?: string | null;
  source: string; // page | claim | signal | kb
}

export interface Rationale {
  why: string;
  kb_factor_ids: string[];
  kb_factor_names: string[]; // resolved names === KBCoverageItem.factor (join key)
  evidence: EvidenceRef[];
  queries_targeted: string[];
  expected_effect: string;
  recommendation_ids: string[];
}

export interface VerificationIssue {
  kind: string;
  detail: string;
  quote?: string;
  block_id?: string | null;
}

export type VerificationStatus = "unverified" | "passed" | "revised" | "needs_human";

export interface VerificationOutcome {
  status: VerificationStatus;
  issues: VerificationIssue[];
  notes?: string;
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

export async function getRun(id: string): Promise<{
  result: AnalysisResult | null;
  status: string;
  error: string | null;
  has_rewrite?: boolean;
  has_optimization?: boolean;
}> {
  const r = await fetch(`${API_BASE}/api/runs/${id}`, { cache: "no-store" });
  return r.json();
}

export interface ProgressEvent {
  step: string;
  message: string;
  pct: number;
}

// ------------------------------------------------------------ Agent streaming
export type StepStatus = "started" | "completed" | "failed" | "skipped";

// One step transition from the agent (SSE event name: "agent_step").
// A repeated step_id is a status transition for the same step.
export interface AgentEvent {
  run_id?: string;
  phase: string; // plan | audit | rewrite | verify | assemble | analysis
  step_id: string;
  title?: string;
  detail?: string | null;
  status: StepStatus;
  ts: string; // ISO-8601
  pct?: number | null;
  meta?: Record<string, unknown> | null;
}

// Stream an analysis: POST multipart, read the text/event-stream response body.
export async function runAnalysis(
  form: FormData,
  handlers: {
    onProgress?: (p: ProgressEvent) => void;
    onAgentEvent?: (e: AgentEvent) => void;
    onResult?: (r: AnalysisResult & { run_id: string }) => void;
    onError?: (msg: string) => void;
    onRun?: (runId: string) => void;
  },
  signal?: AbortSignal
): Promise<void> {
  await streamPOST(
    `${API_BASE}/api/analyze`,
    form,
    (event, data) => {
      const d = data as Record<string, unknown>;
      if (event === "run") handlers.onRun?.(d.run_id as string);
      else if (event === "progress") handlers.onProgress?.(d as unknown as ProgressEvent);
      else if (event === "agent_step") handlers.onAgentEvent?.(d as unknown as AgentEvent);
      else if (event === "result") handlers.onResult?.(d as unknown as AnalysisResult & { run_id: string });
      else if (event === "error") handlers.onError?.(String(d.message));
    },
    signal
  );
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
  rationale?: Rationale | null; // structured why (agent runs)
  verification?: VerificationOutcome | null; // self-verification stamp (agent runs)
}

export interface PageRewrite {
  run_id: string;
  summary: string;
  content_blocks: RewriteBlock[];
  technical_blocks: RewriteBlock[];
  model_key: string;
  origin?: string; // "studio" | "agent"
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

// ------------------------------------------------------- optimization agent
export interface ScoreCard {
  overall_score: number | null;
  heuristic_baseline: number;
  compliance_score: number | null;
  engine_readiness: EngineReadiness[];
}

export interface VerificationReport {
  passed: number;
  revised: number;
  needs_human: number;
  issues_total: number;
  by_kind: Record<string, number>;
}

// Slim payload of the optimize stream's final `result` event — artifacts
// (rewrite, full OptimizationResult) are refetched, not streamed.
export interface OptimizeSummary {
  run_id: string;
  depth: string;
  stats: Record<string, number>;
  before: ScoreCard;
  after: ScoreCard;
  verification: VerificationReport;
  claims_addressed: number;
}

export interface ExpertProfile {
  id: string;
  name: string;
  role: string;
}

export interface KBFactor {
  id: string;
  name: string;
  description: string;
  category: string;
  criteria: string[];
  importance: number;
  applies_to: string;
  source_doc: string;
}

export interface QueryJudgement {
  query: string;
  before_would_cite: boolean;
  after_would_cite: boolean;
  reasoning: string;
}

export interface CitationJudgement {
  before: EngineReadiness[];
  after: EngineReadiness[];
  per_query: QueryJudgement[];
  summary: string;
}

export interface OptimizationResult {
  run_id: string;
  depth: string;
  model_key: string;
  experts: ExpertProfile[];
  factor_set: { kb_hash: string; factors: KBFactor[] };
  plan: {
    strategy_summary: string;
    style_brief: string;
    technical_plan: string[];
    source: string;
  };
  recommendations: Recommendation[];
  kb_coverage: KBCoverageItem[];
  claims: Claim[];
  verification: VerificationReport;
  citation_judgement: CitationJudgement | null;
  before: ScoreCard;
  after: ScoreCard;
  claims_addressed: number;
  stats: Record<string, number>;
  notes: string[];
}

export interface AgentTrace {
  run_id: string;
  kind: "analysis" | "optimize";
  status: "running" | "completed" | "error";
  depth?: string | null;
  model_key?: string;
  started_at: string;
  updated_at: string;
  events: AgentEvent[];
  summary?: Record<string, unknown>;
}

// Run the optimization agent over a saved analysis run (SSE stream).
export async function streamOptimize(
  runId: string,
  opts: { depth: "quick" | "full"; regenerate?: boolean; goalsFile?: File | null; signal?: AbortSignal },
  handlers: {
    onAgentEvent?: (e: AgentEvent) => void;
    onProgress?: (p: ProgressEvent) => void;
    onResult?: (r: OptimizeSummary) => void;
    onError?: (msg: string) => void;
  }
): Promise<void> {
  const params = new URLSearchParams({
    depth: opts.depth,
    regenerate: String(Boolean(opts.regenerate)),
  });
  let body: FormData | null = null;
  if (opts.goalsFile) {
    body = new FormData();
    body.append("goals_file", opts.goalsFile);
  }
  await streamPOST(
    `${API_BASE}/api/runs/${runId}/optimize?${params}`,
    body,
    (event, data) => {
      const d = data as Record<string, unknown>;
      if (event === "agent_step") handlers.onAgentEvent?.(d as unknown as AgentEvent);
      else if (event === "progress") handlers.onProgress?.(d as unknown as ProgressEvent);
      else if (event === "result") handlers.onResult?.(d as unknown as OptimizeSummary);
      else if (event === "error") handlers.onError?.(String(d.message));
    },
    opts.signal
  );
}

// The persisted agent timeline; readable mid-run. null when the run has none (404).
export async function getTrace(
  runId: string,
  kind: "analysis" | "optimize" = "optimize"
): Promise<AgentTrace | null> {
  const r = await fetch(`${API_BASE}/api/runs/${runId}/trace?kind=${kind}`, { cache: "no-store" });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`Failed to load trace (${r.status})`);
  return r.json();
}

export function optimizedPageUrl(runId: string, deployable = true): string {
  return `${API_BASE}/api/runs/${runId}/export-page?deployable=${deployable}`;
}

export function changePackageUrl(runId: string): string {
  return `${API_BASE}/api/runs/${runId}/change-package`;
}

export async function fetchOptimizedHtml(runId: string): Promise<string> {
  const r = await fetch(optimizedPageUrl(runId), { cache: "no-store" });
  if (!r.ok) throw new Error(`Failed to build optimized page (${r.status})`);
  return r.text();
}

// The stored OptimizationResult (+ status). null when the run has none (404).
export async function getOptimization(runId: string): Promise<{
  status: string;
  depth: string;
  result: OptimizationResult | null;
  error: string | null;
} | null> {
  const r = await fetch(`${API_BASE}/api/runs/${runId}/optimization`, { cache: "no-store" });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`Failed to load optimization (${r.status})`);
  return r.json();
}
