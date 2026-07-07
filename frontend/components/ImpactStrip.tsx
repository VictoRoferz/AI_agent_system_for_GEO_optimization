"use client";

// Studio header companion after an agent run: per-engine before→after deltas
// (explicitly predicted), KB-factor coverage, and verification tallies.

import CoverageMeter from "@/components/CoverageMeter";
import { engineLabel, type OptimizationResult } from "@/lib/api";

function scoreColor(v: number): string {
  if (v >= 70) return "text-emerald-700";
  if (v >= 40) return "text-amber-600";
  return "text-rose-600";
}

export default function ImpactStrip({
  optimization,
  runId,
}: {
  optimization: OptimizationResult;
  runId: string;
}) {
  const judge = optimization.citation_judgement;
  const beforeByEngine = new Map(
    (judge?.before?.length ? judge.before : optimization.before.engine_readiness).map((er) => [
      er.engine,
      er.score,
    ])
  );
  const deltas = (judge?.after ?? []).map((er) => ({
    engine: er.engine,
    before: beforeByEngine.get(er.engine) ?? null,
    after: er.score,
  }));
  const v = optimization.verification;

  return (
    <div className="card flex flex-wrap items-start gap-x-8 gap-y-4 p-4">
      {deltas.length > 0 && (
        <div>
          <div className="section-title">
            Citation readiness{" "}
            <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] normal-case text-slate-500">
              predicted
            </span>
          </div>
          <div className="mt-1.5 flex flex-wrap gap-4">
            {deltas.map((d) => (
              <div key={d.engine} className="text-sm">
                <div className="text-[11px] text-slate-500">{engineLabel(d.engine)}</div>
                <div className="flex items-baseline gap-1.5 tabular-nums">
                  {d.before !== null && <span className="text-slate-400">{d.before}</span>}
                  <span className="text-slate-300">→</span>
                  <span className={`font-semibold ${scoreColor(d.after)}`}>{d.after}</span>
                  {d.before !== null && (
                    <span
                      className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                        d.after - d.before >= 0
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-rose-100 text-rose-700"
                      }`}
                    >
                      {d.after - d.before >= 0 ? "+" : ""}
                      {d.after - d.before}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="min-w-56 flex-1">
        <CoverageMeter coverage={optimization.kb_coverage} runId={runId} />
      </div>

      <div>
        <div className="section-title">Self-verification</div>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-700">
            ✓ {v.passed} verified
          </span>
          {v.revised > 0 && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700">
              ⚠ {v.revised} revised
            </span>
          )}
          {v.needs_human > 0 && (
            <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-medium text-rose-700">
              ✗ {v.needs_human} for review
            </span>
          )}
        </div>
        {optimization.claims_addressed > 0 && (
          <p className="mt-1 text-[11px] text-slate-500">
            {optimization.claims_addressed} claim risk{optimization.claims_addressed > 1 ? "s" : ""} addressed
          </p>
        )}
      </div>
    </div>
  );
}
