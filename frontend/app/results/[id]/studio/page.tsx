"use client";

import { use, useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import AskAiButton from "@/components/AskAiButton";
import ChatAgent from "@/components/ChatAgent";
import CopyButton from "@/components/CopyButton";
import DiffPanes from "@/components/DiffPanes";
import OptionTabs from "@/components/OptionTabs";
import TechnicalMap from "@/components/TechnicalMap";
import { ChangeView } from "@/components/Report";
import {
  PRIORITY_COLOR,
  fetchSnapshot,
  generateRewrite,
  getRun,
  getStudio,
  selectOption,
  type ChatMessage,
  type Claim,
  type ClaimFlag,
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
  onRewrite,
  onEdited,
  onNewRecommendations,
}: {
  block: RewriteBlock;
  flash: boolean;
  runId: string;
  claim?: Claim;
  onRewrite: (r: PageRewrite) => void;
  onEdited: (ids: string[]) => void;
  onNewRecommendations: (recs: Recommendation[]) => void;
}) {
  const [why, setWhy] = useState(false);
  const [ask, setAsk] = useState(false);
  const [busy, setBusy] = useState(false);

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
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/70 px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-navy-900">{block.label}</span>
          {block.changed ? (
            <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent-dark">
              changed
            </span>
          ) : (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] uppercase tracking-wide text-slate-400">
              kept
            </span>
          )}
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
            block.changed ? "border-l-2 border-accent" : ""
          } ${flash ? "bg-accent/10" : block.changed ? "bg-accent/[0.04]" : ""}`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-accent-dark">
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
          {block.changed && block.change_explanation && (
            <button
              type="button"
              onClick={() => setWhy((v) => !v)}
              className="mt-2 text-[11px] font-medium text-accent-dark hover:underline"
            >
              {why ? "Hide why" : "Why this changed"}
            </button>
          )}
          {why && block.change_explanation && (
            <p className="mt-1 rounded-md bg-slate-50 p-2 text-xs text-slate-600">
              {block.change_explanation}
            </p>
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
function TechnicalRow({ block, flash }: { block: RewriteBlock; flash: boolean }) {
  return (
    <div className={`card p-4 transition-colors duration-700 ${flash ? "ring-2 ring-accent" : ""}`}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-navy-900">{block.label}</span>
        <CopyButton text={block.proposed} className="border-slate-600 bg-navy-800 text-slate-200" />
      </div>
      <pre className="mt-2 overflow-x-auto rounded-md bg-navy-900 p-3 text-xs leading-relaxed text-slate-100">
        <code>{block.proposed}</code>
      </pre>
      {block.change_explanation && (
        <p className="mt-2 text-xs text-slate-600">{block.change_explanation}</p>
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
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // changed blocks → marks on both live panes (uses the selected option's text).
  const changes = useMemo(
    () =>
      (rewrite?.content_blocks || [])
        .filter((b) => b.changed && (b.original.trim() || b.anchor_id))
        .map((b) => ({
          original: b.original,
          proposed: b.proposed,
          anchorId: b.anchor_id,
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
        if (state.rewrite) {
          setRewrite(state.rewrite);
        } else {
          setGenerating(true);
          const fresh = await generateRewrite(id);
          if (!cancelled) setRewrite(fresh);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) {
          setLoading(false);
          setGenerating(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  function flash(ids: string[]) {
    const real = ids.filter((b) => b !== "new");
    if (!real.length) return;
    setFlashIds(new Set(real));
    setTimeout(() => setFlashIds(new Set()), 1600);
  }

  async function regenerate() {
    setGenerating(true);
    setError(null);
    try {
      setRewrite(await generateRewrite(id, true));
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerating(false);
    }
  }

  if (loading || generating)
    return (
      <div className="card flex flex-col items-center gap-3 p-10 text-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-accent" />
        <p className="text-sm text-slate-600">
          {generating ? "The agent is rewriting the page…" : "Loading studio…"}
        </p>
        <p className="text-xs text-slate-400">This can take a moment for a full rewrite.</p>
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
          <button
            onClick={regenerate}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm hover:border-slate-400"
          >
            ↻ Regenerate
          </button>
          <Link
            href={`/results/${id}`}
            className="rounded-lg bg-navy-800 px-4 py-2 text-sm text-white hover:bg-navy-900"
          >
            ← Back to report
          </Link>
        </div>
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
      {rewrite && <DiffPanes html={snapshotHtml} changes={changes} claims={claims} url={url} />}

      {/* Content rewrite — per block: 3 options, claim flag, ask-AI */}
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
          {rewrite?.content_blocks.map((b) => (
            <ContentRow
              key={b.id}
              block={b}
              flash={flashIds.has(b.id)}
              runId={id}
              claim={resolveClaim(b)}
              onRewrite={setRewrite}
              onEdited={flash}
              onNewRecommendations={setSuggestions}
            />
          ))}
          {!rewrite?.content_blocks.length && (
            <p className="text-sm text-slate-400">No content blocks were produced.</p>
          )}
        </div>
      </div>

      {/* Technical: structure & metadata map (original vs proposed) */}
      {rewrite && (
        <div>
          <h2 className="section-title mb-2">Technical structure & metadata</h2>
          <TechnicalMap signals={signals} rewrite={rewrite} />
        </div>
      )}

      {/* Technical changes — exact code to ship */}
      {rewrite && rewrite.technical_blocks.length > 0 && (
        <div>
          <h2 className="section-title mb-2">Technical changes — code</h2>
          <div className="space-y-3">
            {rewrite.technical_blocks.map((b) => (
              <TechnicalRow key={b.id} block={b} flash={flashIds.has(b.id)} />
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
    </div>
  );
}
