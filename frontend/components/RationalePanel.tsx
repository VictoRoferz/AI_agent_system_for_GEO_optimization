"use client";

// The unified "Why this change?" renderer — used identically by content blocks,
// technical blocks and recommendation cards, fixing the old inconsistency where
// only some changes explained themselves.

import Link from "next/link";
import VerificationBadge from "@/components/VerificationBadge";
import { EXPERT_META } from "@/components/AgentTimeline";
import type { Rationale, VerificationOutcome } from "@/lib/api";

export function slugifyFactor(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

export default function RationalePanel({
  rationale,
  verification,
  legacyExplanation,
  sourceAgent,
  runId,
  compact = false,
}: {
  rationale?: Rationale | null;
  verification?: VerificationOutcome | null;
  legacyExplanation?: string | null;
  sourceAgent?: string | null;
  runId: string;
  compact?: boolean;
}) {
  const why = rationale?.why || legacyExplanation || "";
  const hasAnything =
    Boolean(why) ||
    Boolean(rationale?.kb_factor_names?.length) ||
    Boolean(rationale?.evidence?.length) ||
    Boolean(verification && verification.status !== "unverified");

  if (!hasAnything) {
    return (
      <p className="rounded-md bg-slate-50 p-3 text-xs italic text-slate-400">
        No rationale was recorded for this change.
      </p>
    );
  }

  const expert = sourceAgent ? EXPERT_META[sourceAgent] ?? sourceAgent : null;

  return (
    <div className={`rounded-md bg-slate-50 ${compact ? "p-2 space-y-1.5" : "p-3 space-y-2"}`}>
      {why && <p className="text-xs text-slate-700">{why}</p>}

      {(expert || (verification && verification.status !== "unverified")) && (
        <div className="flex flex-wrap items-center gap-1.5">
          {expert && (
            <span className="rounded-full bg-navy-50 px-2 py-0.5 text-[10px] font-medium text-navy-700">
              Found by {expert}
            </span>
          )}
          <VerificationBadge status={verification?.status} />
        </div>
      )}

      {Boolean(rationale?.kb_factor_names?.length) && (
        <div>
          <div className="section-title">KB factors</div>
          <div className="mt-1 flex flex-wrap gap-1">
            {rationale!.kb_factor_names.map((name) => (
              <Link
                key={name}
                href={`/results/${runId}#kb-${slugifyFactor(name)}`}
                className="rounded-full bg-navy-50 px-2 py-0.5 text-[10px] text-navy-700 hover:bg-navy-100"
              >
                {name}
              </Link>
            ))}
          </div>
        </div>
      )}

      {Boolean(rationale?.evidence?.length) && (
        <div>
          <div className="section-title">Evidence from the page</div>
          <div className="mt-1 space-y-1">
            {rationale!.evidence.slice(0, 4).map((e, i) => (
              <blockquote
                key={i}
                className="border-l-2 border-slate-300 pl-2 text-xs italic text-slate-600"
              >
                “{e.quote}”
                {e.source !== "page" && (
                  <span className="ml-1 not-italic text-[10px] text-slate-400">({e.source})</span>
                )}
              </blockquote>
            ))}
          </div>
        </div>
      )}

      {Boolean(rationale?.queries_targeted?.length) && (
        <div>
          <div className="section-title">Targets queries</div>
          <div className="mt-1 flex flex-wrap gap-1">
            {rationale!.queries_targeted.map((q) => (
              <span key={q} className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] text-accent-dark">
                {q}
              </span>
            ))}
          </div>
        </div>
      )}

      {rationale?.expected_effect && (
        <div>
          <div className="section-title">Expected effect</div>
          <p className="mt-0.5 text-xs text-slate-600">{rationale.expected_effect}</p>
        </div>
      )}

      {Boolean(verification?.issues?.length) && (
        <div>
          <div className="section-title">Verification notes</div>
          <ul className="mt-1 space-y-0.5">
            {verification!.issues.slice(0, 5).map((issue, i) => (
              <li key={i} className="text-[11px] text-slate-600">
                <span className="font-medium text-slate-500">[{issue.kind}]</span> {issue.detail}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
