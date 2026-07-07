"use client";

import { use, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import AgentTimeline from "@/components/AgentTimeline";
import Report from "@/components/Report";
import { reduceAgentEvents } from "@/lib/useAgentStream";
import { getRun, getTrace, type AgentTrace, type AnalysisResult } from "@/lib/api";

export default function ResultsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [trace, setTrace] = useState<AgentTrace | null>(null);
  const [hasRewrite, setHasRewrite] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getRun(id)
      .then((r) => {
        if (r.status === "error") setError(r.error || "Analysis failed");
        else {
          setResult(r.result);
          setHasRewrite(Boolean(r.has_rewrite));
        }
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
    getTrace(id)
      .then(setTrace)
      .catch(() => undefined);
  }, [id]);

  const tracePhases = useMemo(() => reduceAgentEvents(trace?.events || []), [trace]);

  if (loading) return <p className="text-slate-500">Loading report…</p>;
  if (error)
    return (
      <div className="card p-6">
        <h2 className="font-semibold text-priority-p0">Analysis failed</h2>
        <p className="mt-2 text-sm text-slate-600">{error}</p>
        <Link href="/" className="mt-4 inline-block text-accent hover:underline">
          ← Start a new analysis
        </Link>
      </div>
    );
  if (!result) return <p className="text-slate-500">No result found.</p>;

  return (
    <div className="space-y-6">
      {trace && trace.status !== "running" && (
        <div className="no-print">
          <AgentTimeline
            phases={tracePhases}
            status={trace.status === "error" ? "error" : "done"}
            depth={trace.depth === "full" ? "full" : trace.depth === "quick" ? "quick" : undefined}
            startedAt={trace.started_at}
            finishedAt={trace.updated_at}
            title="Optimization agent — this page has an optimized version"
            defaultCollapsed
          />
        </div>
      )}
      <Report result={result} runId={id} hasRewrite={hasRewrite} />
    </div>
  );
}
