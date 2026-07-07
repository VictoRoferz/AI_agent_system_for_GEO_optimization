"use client";

// "28/31 KB factors addressed" — fraction bar + optional per-factor chips.

import Link from "next/link";
import { slugifyFactor } from "@/components/RationalePanel";
import type { KBCoverageItem } from "@/lib/api";

export default function CoverageMeter({
  coverage,
  runId,
}: {
  coverage: KBCoverageItem[];
  runId?: string;
}) {
  if (!coverage.length) return null;
  const addressed = coverage.filter((c) => c.status === "covered" || (c.related_rec_ids?.length ?? 0) > 0 || (c.related_block_ids?.length ?? 0) > 0);
  const pct = Math.round((addressed.length / coverage.length) * 100);
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-semibold text-navy-900">
          {addressed.length}/{coverage.length} KB factors addressed
        </span>
        <span className="text-[10px] tabular-nums text-slate-400">{pct}%</span>
      </div>
      <div className="mt-1 h-2 w-full rounded-full bg-slate-200">
        <div className="h-2 rounded-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
      <details className="mt-1.5">
        <summary className="cursor-pointer text-[11px] text-slate-500 hover:text-slate-700">
          Show factors
        </summary>
        <div className="mt-1.5 flex flex-wrap gap-1">
          {coverage.map((c) => {
            const done = addressed.includes(c);
            const chip = (
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] ${
                  done ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"
                }`}
                title={c.assessment}
              >
                {done ? "✓ " : ""}
                {c.factor}
              </span>
            );
            return runId ? (
              <Link key={c.factor} href={`/results/${runId}#kb-${slugifyFactor(c.factor)}`}>
                {chip}
              </Link>
            ) : (
              <span key={c.factor}>{chip}</span>
            );
          })}
        </div>
      </details>
    </div>
  );
}
