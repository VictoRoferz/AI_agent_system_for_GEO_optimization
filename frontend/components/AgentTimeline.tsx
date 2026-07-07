"use client";

// Live/replay activity feed for the GEO agent: phases as groups, steps as rows
// with status glyphs, durations, expert attribution and expandable detail.
// Works both on live SSE streams (via useAgentStream) and persisted traces.

import { useEffect, useRef, useState } from "react";
import BrainPoints from "@/components/BrainPoints";
import type { StreamStatus, TimelinePhase, TimelineStep } from "@/lib/useAgentStream";

const PHASE_META: Record<string, { glyph: string; label: string }> = {
  analysis: { glyph: "≡", label: "Analysis" },
  plan: { glyph: "◈", label: "Planning" },
  audit: { glyph: "⌕", label: "Audit — KB factors" },
  rewrite: { glyph: "✎", label: "Rewrite" },
  verify: { glyph: "✓", label: "Self-verification" },
  assemble: { glyph: "▣", label: "Finalize & export" },
};

// Expert ids (AgentEvent.meta.agent) → display names, mirroring the backend registry.
export const EXPERT_META: Record<string, string> = {
  strategist: "Senior GEO Strategist",
  technical: "Technical GEO Engineer",
  content: "Content & Answerability Strategist",
  compliance: "Evidence & Compliance Officer",
  brand: "Brand & Entity Visibility Expert",
  fidelity: "Domain Fidelity Guardian",
  retrieval: "LLM Retrieval Expert",
};

const STREAM_CHIP: Record<StreamStatus, { label: string; cls: string }> = {
  idle: { label: "idle", cls: "bg-slate-100 text-slate-500" },
  streaming: { label: "working", cls: "bg-accent/10 text-accent-dark" },
  done: { label: "finished", cls: "bg-emerald-100 text-emerald-700" },
  error: { label: "failed", cls: "bg-rose-100 text-rose-700" },
};

function fmtDur(ms: number): string {
  if (!isFinite(ms) || ms < 0) return "";
  if (ms < 10_000) return `${(ms / 1000).toFixed(1)}s`;
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  const m = Math.floor(ms / 60_000);
  const s = Math.round((ms % 60_000) / 1000);
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

function metaChips(meta: Record<string, unknown> | null): string[] {
  if (!meta) return [];
  const chips: string[] = [];
  if (typeof meta.factors_done === "number" && typeof meta.factors_total === "number")
    chips.push(`${meta.factors_done}/${meta.factors_total} factors`);
  if (typeof meta.factor === "string" && meta.factor) chips.push(meta.factor);
  if (Array.isArray(meta.block_ids) && meta.block_ids.length)
    chips.push(`${meta.block_ids.length} block${meta.block_ids.length > 1 ? "s" : ""}`);
  if (meta.counts && typeof meta.counts === "object")
    for (const [k, v] of Object.entries(meta.counts as Record<string, unknown>))
      if (typeof v === "number") chips.push(`${v} ${k}`);
  return chips;
}

function StatusIcon({ status }: { status: string }) {
  if (status === "started")
    return (
      <span
        className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-200 border-t-accent motion-reduce:animate-none"
        aria-hidden
      />
    );
  if (status === "completed")
    return <span className="text-xs font-bold text-emerald-600" aria-hidden>✓</span>;
  if (status === "failed")
    return <span className="text-xs font-bold text-rose-600" aria-hidden>✗</span>;
  return <span className="text-xs text-slate-300" aria-hidden>–</span>;
}

function StepRow({ step }: { step: TimelineStep }) {
  const [manual, setManual] = useState<boolean | null>(null);
  const findings = Array.isArray(step.meta?.findings) ? (step.meta!.findings as string[]) : [];
  const expandable = Boolean(step.detail || findings.length);
  // The running step is forced open; it auto-closes on completion unless pinned open.
  const open = manual ?? step.status === "started";
  const dur = step.ts_end ? Date.parse(step.ts_end) - Date.parse(step.ts_start) : null;
  const agentId = typeof step.meta?.agent === "string" ? (step.meta.agent as string) : null;
  const expert = agentId ? EXPERT_META[agentId] ?? agentId : null;
  const chips = metaChips(step.meta);

  return (
    <div className="relative pl-6 py-1.5">
      <span className="absolute bottom-0 left-2 top-0 w-px bg-slate-200" aria-hidden />
      <span className="absolute left-2 top-2.5 flex h-4 w-4 -translate-x-1/2 items-center justify-center rounded-full bg-white">
        <StatusIcon status={step.status} />
      </span>
      <div className="flex items-baseline gap-2">
        <span
          className={`text-sm ${step.status === "failed" ? "text-rose-700" : "text-navy-900"}`}
        >
          {step.title}
        </span>
        {expert && (
          <span className="rounded-full bg-navy-50 px-2 py-0.5 text-[10px] font-medium text-navy-700">
            {expert}
          </span>
        )}
        {expandable && (
          <button
            type="button"
            onClick={() => setManual(open ? false : true)}
            className="text-[10px] text-slate-400 hover:text-slate-600"
            aria-expanded={open}
          >
            {open ? "▾" : "▸"}
          </button>
        )}
        <span className="ml-auto text-[10px] tabular-nums text-slate-400">
          {dur !== null ? fmtDur(dur) : ""}
        </span>
      </div>
      {chips.length > 0 && (
        <div className="mt-0.5 flex flex-wrap gap-1">
          {chips.map((c, i) => (
            <span
              key={i}
              className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500"
            >
              {c}
            </span>
          ))}
        </div>
      )}
      {open && expandable && (
        <div className="mt-1 rounded-md bg-slate-50 p-2 text-xs text-slate-600">
          {step.detail && <p>{step.detail}</p>}
          {findings.length > 0 && (
            <ul className="mt-1 list-disc pl-4">
              {findings.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default function AgentTimeline({
  phases,
  status,
  error = null,
  progressPct = null,
  depth,
  startedAt,
  finishedAt,
  title = "Agent activity",
  defaultCollapsed = false,
  maxHeightClass = "max-h-[420px]",
}: {
  phases: TimelinePhase[];
  status: StreamStatus;
  error?: string | null;
  progressPct?: number | null;
  depth?: "quick" | "full";
  startedAt?: string | null;
  finishedAt?: string | null;
  title?: string;
  defaultCollapsed?: boolean;
  maxHeightClass?: string;
}) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const [nowTick, setNowTick] = useState(() => Date.now());
  const bodyRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);
  const [pinned, setPinned] = useState(true);

  const streaming = status === "streaming";
  const stepCount = phases.reduce((n, p) => n + p.steps.length, 0);

  // Elapsed clock, ticking only while streaming.
  useEffect(() => {
    if (!streaming) return;
    const t = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(t);
  }, [streaming]);
  const endMs = finishedAt ? Date.parse(finishedAt) : nowTick;
  const elapsed = startedAt ? endMs - Date.parse(startedAt) : null;

  // Auto-scroll to the newest step while the user is pinned to the bottom.
  useEffect(() => {
    if (!pinnedRef.current || collapsed) return;
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
  }, [stepCount, status, collapsed]);

  function onScroll() {
    const el = bodyRef.current;
    if (!el) return;
    const p = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    pinnedRef.current = p;
    setPinned(p);
  }

  // Latest transition, announced once via a polite live region.
  const flat = phases.flatMap((p) => p.steps);
  const current =
    [...flat].reverse().find((s) => s.status === "started") ?? flat[flat.length - 1];
  const liveText = current
    ? `${PHASE_META[current.phase]?.label ?? current.phase}: ${current.title} — ${current.status}`
    : "";

  const chip = STREAM_CHIP[status];

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50/70 px-3 py-2">
        <BrainPoints size={16} className={streaming ? "text-accent" : "text-slate-400"} />
        <span className="text-sm font-semibold text-navy-900">{title}</span>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${chip.cls}`}
        >
          {chip.label}
        </span>
        {depth && (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500">
            {depth === "quick" ? "quick pass" : "full depth"}
          </span>
        )}
        <span className="ml-auto text-[10px] tabular-nums text-slate-400">
          {collapsed ? `${stepCount} steps${elapsed !== null ? ` · ${fmtDur(elapsed)}` : ""}` : elapsed !== null ? fmtDur(elapsed) : ""}
        </span>
        {!streaming && stepCount > 0 && (
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            className="rounded px-1.5 text-xs text-slate-400 hover:bg-slate-200 hover:text-slate-600"
            aria-expanded={!collapsed}
            title={collapsed ? "Expand timeline" : "Collapse timeline"}
          >
            {collapsed ? "▢" : "—"}
          </button>
        )}
      </div>

      {!collapsed && typeof progressPct === "number" && streaming && (
        <div className="h-1.5 w-full bg-slate-200">
          <div
            className="h-1.5 bg-accent transition-all"
            style={{ width: `${Math.max(0, Math.min(100, progressPct))}%` }}
          />
        </div>
      )}

      <p className="sr-only" aria-live="polite">
        {liveText}
      </p>

      {!collapsed && (
        <div className="relative">
          <div
            ref={bodyRef}
            onScroll={onScroll}
            role="log"
            className={`overflow-y-auto px-3 py-2 ${maxHeightClass}`}
          >
            {phases.length === 0 && (
              <p className="py-2 text-sm text-slate-400">Waiting for the agent…</p>
            )}
            {phases.map((ph) => {
              const meta = PHASE_META[ph.phase] ?? { glyph: "•", label: ph.phase };
              return (
                <div key={ph.phase} className="py-1">
                  <div className="flex items-center gap-2">
                    <span className="section-title">
                      {meta.glyph} {meta.label}
                    </span>
                    <span className="text-[10px] text-slate-400">
                      {ph.steps.filter((s) => s.status !== "started").length}/{ph.steps.length}
                    </span>
                  </div>
                  <div className="mt-1">
                    {ph.steps.map((s) => (
                      <StepRow key={s.step_id} step={s} />
                    ))}
                  </div>
                </div>
              );
            })}
            <div ref={endRef} />
          </div>
          {!pinned && streaming && (
            <button
              type="button"
              onClick={() => {
                pinnedRef.current = true;
                setPinned(true);
                endRef.current?.scrollIntoView({ block: "nearest" });
              }}
              className="absolute bottom-2 right-3 rounded-full bg-navy-800 px-2.5 py-1 text-[10px] font-medium text-white shadow hover:bg-navy-900"
            >
              Jump to latest ↓
            </button>
          )}
        </div>
      )}

      {!collapsed && error && (
        <div className="mx-3 mb-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}
    </div>
  );
}
