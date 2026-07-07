"use client";

import Link from "next/link";
import { slugifyFactor } from "@/components/RationalePanel";
import type { KBCoverageItem, KBCoverageStatus } from "@/lib/api";

const STATUS_META: Record<
  KBCoverageStatus,
  { icon: string; label: string; cls: string }
> = {
  covered: { icon: "✓", label: "Covered", cls: "bg-emerald-100 text-emerald-700" },
  partial: { icon: "⚠", label: "Partial", cls: "bg-amber-100 text-amber-700" },
  gap: { icon: "✗", label: "Gap", cls: "bg-rose-100 text-rose-700" },
};

const ORDER: Record<KBCoverageStatus, number> = { gap: 0, partial: 1, covered: 2 };

export default function KBCoverage({
  items,
  runId,
}: {
  items: KBCoverageItem[];
  runId?: string;
}) {
  if (!items || items.length === 0) return null;

  const sorted = [...items].sort((a, b) => ORDER[a.status] - ORDER[b.status]);
  const counts = items.reduce(
    (acc, it) => ((acc[it.status] = (acc[it.status] || 0) + 1), acc),
    {} as Record<KBCoverageStatus, number>
  );

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h2 className="section-title">
          Knowledge-base coverage ({items.length} factors)
        </h2>
        <div className="flex gap-2 text-[10px]">
          {(Object.keys(STATUS_META) as KBCoverageStatus[]).map((s) =>
            counts[s] ? (
              <span
                key={s}
                className={`rounded-full px-2 py-0.5 font-medium ${STATUS_META[s].cls}`}
              >
                {STATUS_META[s].icon} {counts[s]} {STATUS_META[s].label}
              </span>
            ) : null
          )}
        </div>
      </div>
      <div className="card divide-y divide-slate-100">
        {sorted.map((it, i) => {
          const meta = STATUS_META[it.status];
          return (
            <div
              key={i}
              id={`kb-${slugifyFactor(it.factor)}`}
              className="flex scroll-mt-20 items-start gap-3 p-3"
            >
              <span
                className={`mt-0.5 inline-flex h-6 min-w-6 items-center justify-center rounded-md px-1.5 text-xs font-bold ${meta.cls}`}
                title={meta.label}
              >
                {meta.icon}
              </span>
              <div className="flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-navy-900">{it.factor}</span>
                  {it.related_rec_ids.map((rid) => (
                    <a
                      key={rid}
                      href={`#${rid}`}
                      className="rounded-full bg-navy-50 px-2 py-0.5 text-[10px] text-navy-700 hover:bg-navy-100"
                    >
                      {rid}
                    </a>
                  ))}
                  {runId &&
                    (it.related_block_ids ?? []).map((bid) => (
                      <Link
                        key={bid}
                        href={`/results/${runId}/studio#block-${bid}`}
                        className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] text-accent-dark hover:bg-accent/20"
                        title="See the rewrite block addressing this factor"
                      >
                        {bid} ↗
                      </Link>
                    ))}
                </div>
                <p className="mt-0.5 text-sm text-slate-600">{it.assessment}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
