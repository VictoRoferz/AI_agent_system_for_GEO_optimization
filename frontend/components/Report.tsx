"use client";

import {
  API_BASE,
  engineLabel,
  PRIORITY_COLOR,
  type AnalysisResult,
  type ConcreteChange,
  type EngineReadiness,
  type Recommendation,
} from "@/lib/api";
import CopyButton from "./CopyButton";
import PriorityMatrix from "./PriorityMatrix";
import ScoreGauge from "./ScoreGauge";

export function ChangeView({ change }: { change: ConcreteChange }) {
  if (change.change_type === "technical") {
    const code = change.code_snippet || "";
    return (
      <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="section-title">Apply this — {change.target}</span>
          <span className="rounded-full bg-navy-50 px-2 py-0.5 text-[10px] uppercase text-navy-700">
            {change.code_language || "code"}
          </span>
        </div>
        {code && (
          <div className="relative mt-2">
            <pre className="overflow-x-auto rounded-md bg-navy-900 p-3 text-xs leading-relaxed text-slate-100">
              <code>{code}</code>
            </pre>
            <div className="absolute right-2 top-2">
              <CopyButton text={code} className="border-slate-600 bg-navy-800 text-slate-200" />
            </div>
          </div>
        )}
        {change.instructions.length > 0 && (
          <ol className="mt-2 list-decimal space-y-0.5 pl-5 text-xs text-slate-600">
            {change.instructions.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ol>
        )}
      </div>
    );
  }
  // content rewrite — before → after
  const proposed = change.proposed_text || "";
  return (
    <div className="mt-3 rounded-lg border border-slate-200 p-3">
      <div className="section-title">Suggested rewrite — {change.target}</div>
      {change.original_text ? (
        <div className="mt-2">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Before</div>
          <p className="mt-0.5 rounded-md bg-slate-50 p-2 text-sm text-slate-500 line-through decoration-slate-300">
            {change.original_text}
          </p>
        </div>
      ) : (
        <p className="mt-2 text-xs italic text-slate-400">New content (no existing version).</p>
      )}
      <div className="mt-2">
        <div className="flex items-center justify-between">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-accent-dark">After</div>
          {proposed && <CopyButton text={proposed} />}
        </div>
        <p className="mt-0.5 rounded-md border-l-2 border-accent bg-accent/5 p-2 text-sm text-navy-900">
          {proposed}
        </p>
      </div>
    </div>
  );
}

function EngineCard({ er }: { er: EngineReadiness }) {
  return (
    <div className="card p-4 flex items-center justify-between">
      <div>
        <div className="font-semibold text-navy-900">{engineLabel(er.engine)}</div>
        <span
          className={`mt-1 inline-block rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
            er.status === "observed"
              ? "bg-accent/10 text-accent-dark"
              : "bg-slate-100 text-slate-500"
          }`}
        >
          {er.status}
        </span>
        <p className="mt-2 max-w-xs text-xs text-slate-500">{er.rationale}</p>
      </div>
      <ScoreGauge score={er.score} size={84} />
    </div>
  );
}

function ActionCard({ rec }: { rec: Recommendation }) {
  return (
    <div className="card p-5">
      <div className="flex items-start gap-3">
        <span
          className={`mt-0.5 inline-flex h-7 min-w-7 items-center justify-center rounded-md px-2 text-xs font-bold text-white ${PRIORITY_COLOR[rec.priority]}`}
        >
          {rec.priority}
        </span>
        <div className="flex-1">
          <div className="flex items-center justify-between gap-2">
            <h4 className="font-semibold text-navy-900">
              {rec.priority_rank}. {rec.title}
            </h4>
            {rec.target_engine && (
              <span className="rounded-full bg-navy-50 px-2 py-0.5 text-[10px] text-navy-700">
                {engineLabel(rec.target_engine)}
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-slate-600">{rec.description}</p>

          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div>
              <div className="section-title">Why it matters</div>
              <p className="text-sm text-slate-600">{rec.why_it_matters}</p>
            </div>
            <div>
              <div className="section-title">Expected impact</div>
              <p className="text-sm text-slate-600">{rec.expected_impact}</p>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-500">
            <span>Impact: <b>{rec.impact_score}/5</b></span>
            <span>Effort: <b className="capitalize">{rec.effort}</b></span>
            <span>Confidence: <b>{rec.confidence}/5</b></span>
          </div>

          {rec.change && <ChangeView change={rec.change} />}

          {rec.evidence.length > 0 && (
            <details className="mt-2 text-xs text-slate-500">
              <summary className="cursor-pointer">Evidence</summary>
              <ul className="mt-1 list-disc pl-5">
                {rec.evidence.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Report({ result, runId }: { result: AnalysisResult; runId: string }) {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-navy-900">GEO Analysis Report</h1>
          <a href={result.url} target="_blank" className="text-sm text-accent hover:underline">
            {result.url}
          </a>
          <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-400">
            <span className="rounded bg-slate-100 px-2 py-0.5">mode: {result.mode}</span>
            <span className="rounded bg-slate-100 px-2 py-0.5">model: {result.model_key}</span>
            {result.target_engines.map((e) => (
              <span key={e} className="rounded bg-slate-100 px-2 py-0.5">{engineLabel(e)}</span>
            ))}
          </div>
        </div>
        <div className="no-print flex flex-wrap gap-2">
          <a
            href={`/results/${runId}/studio`}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-accent-dark"
          >
            ✨ Open AI Studio
          </a>
          <a
            href={`${API_BASE}/api/runs/${runId}/export?format=md`}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm hover:border-slate-400"
          >
            Export MD
          </a>
          <a
            href={`${API_BASE}/api/runs/${runId}/export?format=pdf`}
            className="rounded-lg bg-navy-800 px-4 py-2 text-sm text-white hover:bg-navy-900"
          >
            Export PDF
          </a>
        </div>
      </div>

      {/* Executive summary + overall score */}
      <div className="card p-6 flex flex-col gap-6 sm:flex-row sm:items-center">
        <ScoreGauge score={result.overall_score} label="Overall GEO score" />
        <div className="flex-1">
          <h2 className="section-title">Executive summary</h2>
          <p className="mt-1 text-slate-700 leading-relaxed">{result.executive_summary}</p>
        </div>
      </div>

      {/* Engine readiness */}
      <div>
        <h2 className="section-title mb-2">Citation readiness by engine</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {result.engine_readiness.map((er) => (
            <EngineCard key={er.engine} er={er} />
          ))}
        </div>
      </div>

      {/* Alignment + matrix */}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card p-5">
          <h3 className="section-title mb-3">Strategic alignment</h3>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-sm">
                <span className="font-medium text-navy-900">Goal alignment</span>
                <span>{result.alignment.goal_alignment_score}/100</span>
              </div>
              <div className="mt-1 h-2 rounded-full bg-slate-200">
                <div
                  className="h-2 rounded-full bg-accent"
                  style={{ width: `${result.alignment.goal_alignment_score}%` }}
                />
              </div>
              <p className="mt-1 text-sm text-slate-600">{result.alignment.goal_alignment_summary}</p>
            </div>
            <div>
              <div className="flex justify-between text-sm">
                <span className="font-medium text-navy-900">Query coverage</span>
                <span>{result.alignment.query_coverage_score}/100</span>
              </div>
              <div className="mt-1 h-2 rounded-full bg-slate-200">
                <div
                  className="h-2 rounded-full bg-navy-700"
                  style={{ width: `${result.alignment.query_coverage_score}%` }}
                />
              </div>
              <p className="mt-1 text-sm text-slate-600">{result.alignment.query_coverage_summary}</p>
            </div>
            {result.alignment.gaps.length > 0 && (
              <div>
                <div className="section-title">Gaps</div>
                <ul className="mt-1 list-disc pl-5 text-sm text-slate-600">
                  {result.alignment.gaps.map((g, i) => (
                    <li key={i}>{g}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
        <PriorityMatrix recs={result.recommendations} />
      </div>

      {/* Recommendations */}
      <div>
        <h2 className="section-title mb-2">
          Prioritized recommendations ({result.recommendations.length})
        </h2>
        <div className="space-y-3">
          {result.recommendations.map((rec) => (
            <ActionCard key={rec.id} rec={rec} />
          ))}
        </div>
      </div>

      {/* Notes */}
      {result.notes.length > 0 && (
        <div className="card p-4 bg-amber-50 border-amber-200">
          <div className="section-title text-amber-700">Notes</div>
          <ul className="mt-1 list-disc pl-5 text-sm text-amber-800">
            {result.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
