"use client";

// useAgentStream — accumulates agent_step (and legacy progress) events into an
// ordered phase/step timeline. The reducer is pure and keyed by step_id, so
// re-ingesting the same events (e.g. from a persisted trace) is idempotent.
// `resume` polls the server-persisted trace (the source of truth) so a page
// reload mid-run reattaches to the running agent.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getTrace, type AgentEvent, type ProgressEvent, type StepStatus } from "@/lib/api";

export interface TimelineStep {
  step_id: string;
  phase: string;
  title: string;
  detail: string | null;
  status: StepStatus;
  ts_start: string;
  ts_end: string | null;
  meta: Record<string, unknown> | null;
}

export interface TimelinePhase {
  phase: string;
  steps: TimelineStep[];
  status: StepStatus;
}

export type StreamStatus = "idle" | "streaming" | "done" | "error";

const TERMINAL: StepStatus[] = ["completed", "failed", "skipped"];

// Pure: fold raw events into phases (first-seen order) of steps (first-seen order).
export function reduceAgentEvents(events: AgentEvent[]): TimelinePhase[] {
  const steps = new Map<string, TimelineStep>();
  const phaseOrder: string[] = [];
  const phaseSteps = new Map<string, string[]>();

  for (const e of events) {
    if (!e || !e.step_id) continue;
    const existing = steps.get(e.step_id);
    if (!existing) {
      steps.set(e.step_id, {
        step_id: e.step_id,
        phase: e.phase || "analysis",
        title: e.title || e.step_id,
        detail: e.detail ?? null,
        status: e.status,
        ts_start: e.ts,
        ts_end: TERMINAL.includes(e.status) ? e.ts : null,
        meta: e.meta ?? null,
      });
      const phase = e.phase || "analysis";
      if (!phaseSteps.has(phase)) {
        phaseSteps.set(phase, []);
        phaseOrder.push(phase);
      }
      phaseSteps.get(phase)!.push(e.step_id);
    } else {
      existing.status = e.status;
      if (e.title) existing.title = e.title;
      if (e.detail) existing.detail = e.detail;
      if (e.meta) existing.meta = { ...(existing.meta ?? {}), ...e.meta };
      if (TERMINAL.includes(e.status)) existing.ts_end = e.ts;
    }
  }

  return phaseOrder.map((phase) => {
    const ss = (phaseSteps.get(phase) ?? []).map((id) => steps.get(id)!);
    let status: StepStatus = "completed";
    if (ss.some((s) => s.status === "failed")) status = "failed";
    else if (ss.some((s) => s.status === "started")) status = "started";
    else if (ss.length > 0 && ss.every((s) => s.status === "skipped")) status = "skipped";
    return { phase, steps: ss, status };
  });
}

// Pure legacy adapter: synthesize agent events from the analysis ProgressEvent
// stream (fetch → kb → mode → synthesis → done). A new step completes the
// previous one; "done" only closes the last step (no row of its own).
export function progressToEvents(
  p: ProgressEvent,
  prevStepId: string | null,
  now: string
): AgentEvent[] {
  const out: AgentEvent[] = [];
  if (prevStepId && prevStepId !== p.step) {
    out.push({ phase: "analysis", step_id: prevStepId, status: "completed", ts: now });
  }
  if (p.step === "done") return out;
  out.push({
    phase: "analysis",
    step_id: p.step,
    title: p.message,
    status: "started",
    ts: now,
    pct: p.pct,
  });
  return out;
}

export function useAgentStream() {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const [finishedAt, setFinishedAt] = useState<string | null>(null);
  const eventsRef = useRef<AgentEvent[]>([]);
  const prevProgressStep = useRef<string | null>(null);

  const push = useCallback((evs: AgentEvent[]) => {
    if (!evs.length) return;
    eventsRef.current = [...eventsRef.current, ...evs];
    setEvents(eventsRef.current);
  }, []);

  const begin = useCallback(() => {
    eventsRef.current = [];
    prevProgressStep.current = null;
    setEvents([]);
    setStatus("streaming");
    setError(null);
    setProgress(null);
    setStartedAt(new Date().toISOString());
    setFinishedAt(null);
  }, []);

  const ingest = useCallback(
    (e: AgentEvent) => {
      push([e]);
      if (typeof e.pct === "number") {
        setProgress({ step: e.step_id, message: e.title || "", pct: e.pct });
      }
    },
    [push]
  );

  const ingestProgress = useCallback(
    (p: ProgressEvent) => {
      setProgress(p);
      push(progressToEvents(p, prevProgressStep.current, new Date().toISOString()));
      prevProgressStep.current = p.step === "done" ? null : p.step;
    },
    [push]
  );

  // Legacy pct-only update (optimize stream): drive the thin bar without
  // synthesizing timeline rows (agent_step events carry the real timeline).
  const ingestPct = useCallback((p: ProgressEvent) => {
    setProgress(p);
  }, []);

  // Bulk-load a persisted trace (idempotent — the reducer keys by step_id).
  const ingestTrace = useCallback(
    (traceEvents: AgentEvent[]) => {
      eventsRef.current = traceEvents;
      setEvents(traceEvents);
    },
    []
  );

  const finish = useCallback(
    (err?: string) => {
      const now = new Date().toISOString();
      // Close any still-running steps: completed on success, failed on error.
      const open = reduceAgentEvents(eventsRef.current)
        .flatMap((ph) => ph.steps)
        .filter((s) => s.status === "started");
      push(
        open.map((s) => ({
          phase: s.phase,
          step_id: s.step_id,
          status: (err ? "failed" : "completed") as StepStatus,
          ts: now,
        }))
      );
      setStatus(err ? "error" : "done");
      setError(err ?? null);
      setFinishedAt(now);
    },
    [push]
  );

  // Reattach to a run in progress (page reload): poll the persisted trace
  // every 2.5s until it leaves "running", then hand back the terminal status.
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const resume = useCallback(
    (runId: string, kind: "analysis" | "optimize", onDone?: (status: string) => void) => {
      stopPolling();
      eventsRef.current = [];
      setEvents([]);
      setStatus("streaming");
      setError(null);
      const poll = async () => {
        try {
          const trace = await getTrace(runId, kind);
          if (!trace) {
            stopPolling();
            setStatus("idle");
            onDone?.("missing");
            return;
          }
          setStartedAt(trace.started_at);
          ingestTrace(trace.events || []);
          if (trace.status !== "running") {
            stopPolling();
            setStatus(trace.status === "error" ? "error" : "done");
            setFinishedAt(trace.updated_at);
            onDone?.(trace.status);
          }
        } catch {
          // transient — keep polling
        }
      };
      void poll();
      pollRef.current = setInterval(poll, 2500);
    },
    [ingestTrace, stopPolling]
  );

  useEffect(() => stopPolling, [stopPolling]);

  const phases = useMemo(() => reduceAgentEvents(events), [events]);

  return {
    phases,
    status,
    error,
    progress,
    startedAt,
    finishedAt,
    begin,
    ingest,
    ingestProgress,
    ingestPct,
    ingestTrace,
    finish,
    resume,
    stopPolling,
  };
}
