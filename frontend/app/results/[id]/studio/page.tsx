"use client";

import { use, useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import AgentTimeline from "@/components/AgentTimeline";
import AskAiButton from "@/components/AskAiButton";
import ChatAgent from "@/components/ChatAgent";
import CopyButton from "@/components/CopyButton";
import DiffPanes from "@/components/DiffPanes";
import ExportMenu from "@/components/ExportMenu";
import ImpactStrip from "@/components/ImpactStrip";
import OptimizeLauncher from "@/components/OptimizeLauncher";
import OptionTabs from "@/components/OptionTabs";
import RationalePanel from "@/components/RationalePanel";
import TechnicalMap from "@/components/TechnicalMap";
import VerificationBadge from "@/components/VerificationBadge";
import { ChangeView } from "@/components/Report";
import { reduceAgentEvents, useAgentStream } from "@/lib/useAgentStream";
import {
  PRIORITY_COLOR,
  fetchSnapshot,
  getOptimization,
  getRun,
  getStudio,
  getTrace,
  selectOption,
  streamOptimize,
  type AgentTrace,
  type ChatMessage,
  type Claim,
  type ClaimFlag,
  type OptimizationResult,
  type PageRewrite,
  type PageSignals,
  type ProposedFlag,
  type Recommendation,
  type RewriteBlock,
} from "@/lib/api";

const CLAIM_META: Record<
  ClaimFlag,
  { icon: string; short: string; label: string; chip: string; badge: string }
> = {
  red: {
    icon: "🔴",
    short: "Needs proof",
    label: "Proof required — this statement needs a study or citation",
    chip: "bg-rose-100 text-rose-700",
    badge: "border-rose-400 bg-rose-50 text-rose-800",
  },
  yellow: {
    icon: "🟡",
    short: "Add citation",
    label: "Add a citation to strengthen this statement",
    chip: "bg-amber-100 text-amber-700",
    badge: "border-amber-400 bg-amber-50 text-amber-800",
  },
  green: {
    icon: "🟢",
    short: "Proven",
    label: "Proven — no extra study needed",
    chip: "bg-emerald-100 text-emerald-700",
    badge: "border-emerald-400 bg-emerald-50 text-emerald-800",
  },
};

// Inline highlight colors for flagged spans inside the recommended text.
const FLAG_HL: Record<ClaimFlag, string> = {
  red: "bg-rose-200/70 text-rose-900 decoration-rose-500",
  yellow: "bg-amber-200/70 text-amber-900 decoration-amber-500",
  green: "bg-emerald-200/60 text-emerald-900 decoration-emerald-500",
};

// Render `text` with every flagged statement/number wrapped in a colored, underlined span.
function FlaggedText({ text, flags }: { text: string; flags: ProposedFlag[] }) {
  if (!text) return <span className="italic text-slate-300">— empty —</span>;
  // Locate each flag's quote (first unused, non-overlapping occurrence).
  const spans: { start: number; end: number; flag: ClaimFlag; note: string }[] = [];
  const taken: [number, number][] = [];
  for (const f of flags || []) {
    if (!f.quote) continue;
    let from = 0;
    while (from <= text.length) {
      const i = text.indexOf(f.quote, from);
      if (i < 0) break;
      const j = i + f.quote.length;
      if (!taken.some(([s, e]) => i < e && j > s)) {
        spans.push({ start: i, end: j, flag: f.flag, note: f.note });
        taken.push([i, j]);
        break;
      }
      from = i + 1;
    }
  }
  spans.sort((a, b) => a.start - b.start);

  const out: ReactNode[] = [];
  let cur = 0;
  spans.forEach((s, k) => {
    if (s.start > cur) out.push(text.slice(cur, s.start));
    out.push(
      <mark
        key={k}
        title={s.note}
        className={`cursor-help rounded-sm px-0.5 underline decoration-dotted underline-offset-2 ${FLAG_HL[s.flag]}`}
      >
        {text.slice(s.start, s.end)}
      </mark>
    );
    cur = s.end;
  });
  if (cur < text.length) out.push(text.slice(cur));
  return <span className="whitespace-pre-wrap">{out}</span>;
}

// Compact, explicit list of the flagged statements (so it's clear without hovering).
function FlagList({ flags }: { flags: ProposedFlag[] }) {
  if (!flags?.length) return null;
  return (
    <ul className="mt-2 space-y-1">
      {flags.map((f, i) => (
        <li key={i} className="flex items-start gap-1.5 text-[11px] leading-snug">
          <span>{CLAIM_META[f.flag].icon}</span>
          <span className="text-slate-600">
            <span className="font-medium text-slate-700">“{f.quote}”</span>
            {f.note ? ` — ${f.note}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

// --- one original→proposed content block (paired columns, GitHub-style) -----
function ContentRow({
  block,
  flash,
  runId,
  claim,
  forceWhy = false,
  onRewrite,
  onEdited,
  onNewRecommendations,
}: {
  block: RewriteBlock;
  flash: boolean;
  runId: string;
  claim?: Claim;
  forceWhy?: boolean;
  onRewrite: (r: PageRewrite) => void;
  onEdited: (ids: string[]) => void;
  onNewRecommendations: (recs: Recommendation[]) => void;
}) {
  const [why, setWhy] = useState(false);
  const [ask, setAsk] = useState(false);
  const [busy, setBusy] = useState(false);

  // A "?" click in the diff panes (or a #block- deep link) opens the rationale.
  useEffect(() => {
    if (forceWhy) setWhy(true);
  }, [forceWhy]);

  async function pick(index: number) {
    if (index === block.selected_option_index) return;
    setBusy(true);
    try {
      onRewrite(await selectOption(runId, block.id, index));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div id={`block-${block.id}`} className="card scroll-mt-20 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/70 px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-navy-900">{block.label}</span>
          {block.changed ? (
            <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-700">
              optimized
            </span>
          ) : (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] uppercase tracking-wide text-slate-400">
              kept
            </span>
          )}
          <VerificationBadge status={block.verification?.status} />
          {claim && (
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${CLAIM_META[claim.flag].chip}`}
              title={claim.rationale}
            >
              {CLAIM_META[claim.flag].icon} {CLAIM_META[claim.flag].short}
            </span>
          )}
        </div>
        <AskAiButton active={ask} onClick={() => setAsk((v) => !v)} />
      </div>

      <div className="grid gap-px bg-slate-100 lg:grid-cols-2">
        <div className="bg-white p-4">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Original</div>
          <p className="mt-1 whitespace-pre-wrap text-sm text-slate-500">
            {block.original || <span className="italic text-slate-300">— not present —</span>}
          </p>
        </div>
        <div
          className={`bg-white p-4 transition-colors duration-700 ${
            block.changed ? "border-l-2 border-blue-400" : ""
          } ${flash ? "bg-blue-100" : block.changed ? "bg-blue-50" : ""}`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-blue-700">
              Proposed{block.changed ? " ✨" : ""}
            </div>
            <div className="flex items-center gap-2">
              <OptionTabs
                count={block.options?.length || 0}
                selected={block.selected_option_index}
                busy={busy}
                onSelect={pick}
              />
              {block.proposed && <CopyButton text={block.proposed} />}
            </div>
          </div>
          <p className="mt-1 text-sm text-navy-900">
            <FlaggedText text={block.proposed} flags={block.flags} />
          </p>
          <FlagList flags={block.flags} />
          {block.changed && (
            <button
              type="button"
              onClick={() => setWhy((v) => !v)}
              className="mt-2 text-[11px] font-medium text-accent-dark hover:underline"
            >
              {why ? "Hide why" : "Why this change?"}
            </button>
          )}
          {why && block.changed && (
            <div className="mt-1">
              <RationalePanel
                rationale={block.rationale}
                verification={block.verification}
                legacyExplanation={block.change_explanation}
                runId={runId}
              />
            </div>
          )}
        </div>
      </div>

      {ask && (
        <div className="border-t border-slate-100 bg-slate-50/40 p-3">
          <ChatAgent
            runId={runId}
            blockId={block.id}
            variant="inline"
            title="Ask Syte AI engine"
            subtitle={`About: ${block.label} — iterate on this text, attach a document, or ask “why is this recommended?”`}
            placeholder="e.g. “make it shorter”, “embed the attached study”, “why this wording?”"
            onRewrite={onRewrite}
            onEditedBlocks={onEdited}
            onNewRecommendations={onNewRecommendations}
          />
        </div>
      )}
    </div>
  );
}

// --- one technical (code) change block --------------------------------------
function TechnicalRow({
  block,
  flash,
  runId,
  forceWhy = false,
}: {
  block: RewriteBlock;
  flash: boolean;
  runId: string;
  forceWhy?: boolean;
}) {
  const [why, setWhy] = useState(false);
  useEffect(() => {
    if (forceWhy) setWhy(true);
  }, [forceWhy]);
  return (
    <div
      id={`block-${block.id}`}
      className={`card scroll-mt-20 p-4 transition-colors duration-700 ${flash ? "ring-2 ring-blue-400" : ""}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-navy-900">{block.label}</span>
          <VerificationBadge status={block.verification?.status} />
        </div>
        <CopyButton text={block.proposed} className="border-slate-600 bg-navy-800 text-slate-200" />
      </div>
      <pre className="mt-2 overflow-x-auto rounded-md bg-navy-900 p-3 text-xs leading-relaxed text-slate-100">
        <code>{block.proposed}</code>
      </pre>
      <button
        type="button"
        onClick={() => setWhy((v) => !v)}
        className="mt-2 text-[11px] font-medium text-accent-dark hover:underline"
      >
        {why ? "Hide why" : "Why this change?"}
      </button>
      {why && (
        <div className="mt-1">
          <RationalePanel
            rationale={block.rationale}
            verification={block.verification}
            legacyExplanation={block.change_explanation}
            runId={runId}
          />
        </div>
      )}
      {block.original && (
        <details className="mt-2 text-xs text-slate-500">
          <summary className="cursor-pointer">Current markup</summary>
          <pre className="mt-1 overflow-x-auto rounded-md bg-slate-100 p-2 text-[11px] text-slate-600">
            <code>{block.original}</code>
          </pre>
        </details>
      )}
    </div>
  );
}

export default function StudioPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [url, setUrl] = useState("");
  const [signals, setSignals] = useState<PageSignals | null>(null);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [snapshotHtml, setSnapshotHtml] = useState<string>("");
  const [rewrite, setRewrite] = useState<PageRewrite | null>(null);
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [suggestions, setSuggestions] = useState<Recommendation[]>([]);
  const [flashIds, setFlashIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [showLauncher, setShowLauncher] = useState(false);
  const [rerun, setRerun] = useState(false); // launcher shown over an existing rewrite
  const [replayTrace, setReplayTrace] = useState<AgentTrace | null>(null);
  const [optimization, setOptimization] = useState<OptimizationResult | null>(null);
  const [whyBlockId, setWhyBlockId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stream = useAgentStream();
  const optimizing = stream.status === "streaming";

  // changed blocks → marks on both live panes (uses the selected option's text).
  const changes = useMemo(
    () =>
      (rewrite?.content_blocks || [])
        .filter((b) => b.changed && (b.original.trim() || b.anchor_id))
        .map((b) => ({
          original: b.original,
          proposed: b.proposed,
          anchorId: b.anchor_id,
          blockId: b.id,
          flags: b.flags,
        })),
    [rewrite]
  );

  // claim lookup by the page block id it anchors to.
  const claimByAnchor = useMemo(() => {
    const m = new Map<string, Claim>();
    for (const c of claims) if (c.anchor_id) m.set(c.anchor_id, c);
    return m;
  }, [claims]);

  // Match a rewrite block to its claim by anchor id, or (fallback) by text overlap —
  // so the flag shows even when the brain didn't set an anchor.
  function resolveClaim(block: RewriteBlock): Claim | undefined {
    if (block.anchor_id && claimByAnchor.has(block.anchor_id)) return claimByAnchor.get(block.anchor_id);
    const norm = (s: string) => (s || "").replace(/\s+/g, " ").trim().toLowerCase();
    const bo = norm(block.original);
    if (bo.length < 12) return undefined;
    return claims.find((c) => {
      const ct = norm(c.text);
      return ct.length >= 12 && (bo.includes(ct) || ct.includes(bo));
    });
  }

  // Refetch the studio artifacts after an optimization finishes.
  async function reloadStudio() {
    try {
      const state = await getStudio(id);
      setHistory(state.chat_history || []);
      setSuggestions(state.extra_recommendations || []);
      if (state.rewrite) setRewrite(state.rewrite);
      setReplayTrace(await getTrace(id));
      const opt = await getOptimization(id);
      setOptimization(opt?.result ?? null);
    } catch {
      /* keep whatever we have */
    }
  }

  // "?" click in the diff panes / #block- deep link → scroll to the card, open its why.
  function openWhy(blockId: string) {
    setWhyBlockId(blockId);
    document
      .getElementById(`block-${blockId}`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
    flash([blockId]);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const run = await getRun(id);
        if (cancelled) return;
        if (run.status === "error" || !run.result) {
          setError(run.error || "This run has no result to work from.");
          return;
        }
        setUrl(run.result.url);
        setSignals(run.result.page_signals ?? null);
        setClaims(run.result.claims ?? []);
        fetchSnapshot(id)
          .then((snap) => !cancelled && setSnapshotHtml(snap.html || ""))
          .catch(() => !cancelled && setSnapshotHtml(""));
        const state = await getStudio(id);
        if (cancelled) return;
        setHistory(state.chat_history || []);
        setSuggestions(state.extra_recommendations || []);
        if (state.rewrite) setRewrite(state.rewrite);

        // Reattach to a run already in progress (page reload mid-optimization).
        const trace = await getTrace(id);
        if (cancelled) return;
        if (trace?.status === "running") {
          stream.resume(id, "optimize", () => void reloadStudio());
        } else if (trace) {
          setReplayTrace(trace);
          getOptimization(id)
            .then((opt) => !cancelled && setOptimization(opt?.result ?? null))
            .catch(() => undefined);
        }

        // Deep link: /studio#block-blk-3 → open that block's rationale.
        const hash = window.location.hash;
        if (hash.startsWith("#block-")) {
          const bid = hash.slice("#block-".length);
          setTimeout(() => openWhy(bid), 400);
        }

        if (!state.rewrite && trace?.status !== "running") {
          // No rewrite yet: auto-start when ?optimize=1, else show the launcher.
          const qs = new URLSearchParams(window.location.search);
          if (qs.get("optimize") === "1") {
            const depth = qs.get("depth") === "full" ? "full" : "quick";
            startOptimize(depth, null, false);
          } else {
            setShowLauncher(true);
          }
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  function flash(ids: string[]) {
    const real = ids.filter((b) => b !== "new");
    if (!real.length) return;
    setFlashIds(new Set(real));
    setTimeout(() => setFlashIds(new Set()), 1600);
  }

  function startOptimize(depth: "quick" | "full", goalsFile: File | null, regenerate: boolean) {
    setShowLauncher(false);
    setRerun(false);
    setError(null);
    setReplayTrace(null);
    stream.begin();
    void streamOptimize(
      id,
      { depth, regenerate, goalsFile },
      {
        onAgentEvent: stream.ingest,
        onProgress: stream.ingestPct,
        onResult: () => {
          stream.finish();
          void reloadStudio();
        },
        onError: (msg) => stream.finish(msg),
      }
    ).catch((e) => stream.finish(String(e)));
  }

  if (loading)
    return (
      <div className="card flex flex-col items-center gap-3 p-10 text-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-accent motion-reduce:animate-none" />
        <p className="text-sm text-slate-600">Loading studio…</p>
      </div>
    );

  if (error)
    return (
      <div className="card p-6">
        <h2 className="font-semibold text-priority-p0">Studio unavailable</h2>
        <p className="mt-2 text-sm text-slate-600">{error}</p>
        <Link href={`/results/${id}`} className="mt-4 inline-block text-accent hover:underline">
          ← Back to report
        </Link>
      </div>
    );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-navy-900">Syte AI agent — optimize article</h1>
            <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent-dark">
              proposed rewrite
            </span>
          </div>
          <a href={url} target="_blank" className="text-sm text-accent hover:underline">
            {url}
          </a>
        </div>
        <div className="flex gap-2">
          {rewrite && !optimizing && (
            <button
              onClick={() => setRerun(true)}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm hover:border-slate-400"
            >
              ↻ Re-run optimization
            </button>
          )}
          <Link
            href={`/results/${id}`}
            className="rounded-lg bg-navy-800 px-4 py-2 text-sm text-white hover:bg-navy-900"
          >
            ← Back to report
          </Link>
        </div>
      </div>

      {/* Live agent run (or its terminal state) — replaces the old binary spinner */}
      {stream.status !== "idle" && (
        <AgentTimeline
          key={stream.status === "done" ? "replay" : "live"}
          phases={stream.phases}
          status={stream.status}
          error={stream.error}
          progressPct={stream.progress?.pct ?? null}
          startedAt={stream.startedAt}
          finishedAt={stream.finishedAt}
          title="Optimization agent"
          defaultCollapsed={stream.status === "done"}
        />
      )}
      {optimizing && (
        <div className="space-y-3" aria-hidden>
          {[0, 1].map((i) => (
            <div key={i} className="card h-28 animate-pulse bg-slate-100/60 motion-reduce:animate-none" />
          ))}
        </div>
      )}
      {stream.status === "error" && !rewrite && (
        <div className="card p-4 text-sm">
          <button
            onClick={() => setShowLauncher(true)}
            className="rounded-lg bg-accent px-4 py-2 font-medium text-white hover:bg-accent-dark"
          >
            Retry optimization
          </button>
        </div>
      )}

      {/* Launcher: first optimization of this run, or an explicit re-run */}
      {!optimizing && (showLauncher || rerun) && (
        <OptimizeLauncher
          onStart={(depth, goalsFile) => startOptimize(depth, goalsFile, Boolean(rewrite))}
          regenerate={Boolean(rewrite)}
        />
      )}

      {/* Replay of the completed agent run (collapsed strip) */}
      {!optimizing && !showLauncher && !rerun && replayTrace && stream.status === "idle" && (
        <ReplayStrip trace={replayTrace} />
      )}

      {rewrite && !optimizing && !rerun && (
        <>
          {/* Before→after impact, coverage and verification tallies (agent runs) */}
          {optimization && <ImpactStrip optimization={optimization} runId={id} />}

          {/* Ship it: deployable HTML + change package */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="section-title">Export the optimized page</h2>
            <ExportMenu runId={id} />
          </div>

          {/* AI agent at the top (page-wide): ask, attach any document, refine the rewrite live */}
          <ChatAgent
            runId={id}
            title="Syte AI engine"
            subtitle="Ask about the page, attach any document, or request changes — updates the rewrite live."
            initialMessages={history}
            onRewrite={(r) => setRewrite(r)}
            onEditedBlocks={flash}
            onNewRecommendations={setSuggestions}
          />

          {/* Side-by-side: full original (yellow + ▸) vs full proposed (green), scroll-synced */}
          <DiffPanes html={snapshotHtml} changes={changes} claims={claims} url={url} onWhy={openWhy} />

          {/* Content rewrite — per block: options, claim flag, ask-AI */}
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1">
              <h2 className="section-title">Content rewrite</h2>
              <div className="flex flex-wrap gap-3 text-[11px] text-slate-500">
                <span><span className="font-semibold text-emerald-700">🟢 Proven</span> — no study needed</span>
                <span><span className="font-semibold text-amber-700">🟡 Add citation</span> — strengthen it</span>
                <span><span className="font-semibold text-rose-700">🔴 Needs proof</span> — requires a study</span>
              </div>
            </div>
            <div className="space-y-3">
              {rewrite.content_blocks.map((b) => (
                <ContentRow
                  key={b.id}
                  block={b}
                  flash={flashIds.has(b.id)}
                  runId={id}
                  claim={resolveClaim(b)}
                  forceWhy={whyBlockId === b.id}
                  onRewrite={setRewrite}
                  onEdited={flash}
                  onNewRecommendations={setSuggestions}
                />
              ))}
              {!rewrite.content_blocks.length && (
                <p className="text-sm text-slate-400">No content blocks were produced.</p>
              )}
            </div>
          </div>

          {/* Technical: structure & metadata map (original vs proposed) */}
          <div>
            <h2 className="section-title mb-2">Technical structure & metadata</h2>
            <TechnicalMap signals={signals} rewrite={rewrite} />
          </div>

          {/* Technical changes — exact code to ship */}
          {rewrite.technical_blocks.length > 0 && (
            <div>
              <h2 className="section-title mb-2">Technical changes — code</h2>
              <div className="space-y-3">
                {rewrite.technical_blocks.map((b) => (
                  <TechnicalRow
                    key={b.id}
                    block={b}
                    flash={flashIds.has(b.id)}
                    runId={id}
                    forceWhy={whyBlockId === b.id}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Agent suggestions (new recommendations from chat) */}
          {suggestions.length > 0 && (
            <div>
              <h2 className="section-title mb-2">Agent suggestions ({suggestions.length})</h2>
              <div className="space-y-2">
                {suggestions.map((s) => (
                  <div key={s.id} className="card p-4">
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-flex h-6 min-w-6 items-center justify-center rounded px-1.5 text-[11px] font-bold text-white ${PRIORITY_COLOR[s.priority]}`}
                      >
                        {s.priority}
                      </span>
                      <h4 className="font-semibold text-navy-900">{s.title}</h4>
                    </div>
                    <p className="mt-1 text-sm text-slate-600">{s.description}</p>
                    {s.change && <ChangeView change={s.change} />}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// Collapsed, replayable timeline of a persisted agent run.
function ReplayStrip({ trace }: { trace: AgentTrace }) {
  const phases = useMemo(() => reduceAgentEvents(trace.events || []), [trace]);
  return (
    <AgentTimeline
      phases={phases}
      status={trace.status === "error" ? "error" : "done"}
      depth={trace.depth === "full" ? "full" : trace.depth === "quick" ? "quick" : undefined}
      startedAt={trace.started_at}
      finishedAt={trace.updated_at}
      title="Optimization agent — last run"
      defaultCollapsed
    />
  );
}
