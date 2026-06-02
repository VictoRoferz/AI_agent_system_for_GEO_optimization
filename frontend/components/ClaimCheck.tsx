"use client";

import { useState } from "react";
import CopyButton from "./CopyButton";
import type { Claim, ClaimFlag } from "@/lib/api";

const FLAG_META: Record<ClaimFlag, { icon: string; label: string; cls: string; dot: string }> = {
  red: { icon: "✗", label: "Proof required", cls: "bg-rose-100 text-rose-700", dot: "bg-rose-400" },
  yellow: { icon: "⚠", label: "Proof recommended", cls: "bg-amber-100 text-amber-700", dot: "bg-amber-400" },
  green: { icon: "✓", label: "Proven / OK", cls: "bg-emerald-100 text-emerald-700", dot: "bg-emerald-400" },
};

const ORDER: Record<ClaimFlag, number> = { red: 0, yellow: 1, green: 2 };

type FilterMode = "all" | "red" | "redyellow";

export default function ClaimCheck({ items }: { items: Claim[] }) {
  const [filter, setFilter] = useState<FilterMode>("all");
  if (!items || items.length === 0) return null;

  const counts = items.reduce(
    (acc, it) => ((acc[it.flag] = (acc[it.flag] || 0) + 1), acc),
    {} as Record<ClaimFlag, number>
  );

  const visible = items
    .filter((it) =>
      filter === "all" ? true : filter === "red" ? it.flag === "red" : it.flag !== "green"
    )
    .sort((a, b) => ORDER[a.flag] - ORDER[b.flag]);

  const FilterBtn = ({ mode, label }: { mode: FilterMode; label: string }) => (
    <button
      type="button"
      onClick={() => setFilter(mode)}
      className={`rounded-full px-2 py-0.5 text-[10px] font-medium transition ${
        filter === mode ? "bg-navy-800 text-white" : "bg-slate-100 text-slate-500 hover:bg-slate-200"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h2 className="section-title">Claim &amp; evidence check ({items.length} claims)</h2>
        <div className="flex gap-2 text-[10px]">
          {(["red", "yellow", "green"] as ClaimFlag[]).map((f) =>
            counts[f] ? (
              <span key={f} className={`rounded-full px-2 py-0.5 font-medium ${FLAG_META[f].cls}`}>
                {FLAG_META[f].icon} {counts[f]} {FLAG_META[f].label}
              </span>
            ) : null
          )}
        </div>
        <div className="ml-auto flex items-center gap-1">
          <span className="text-[10px] uppercase tracking-wide text-slate-400">Show</span>
          <FilterBtn mode="all" label="All" />
          <FilterBtn mode="redyellow" label="Needs proof" />
          <FilterBtn mode="red" label="Only 🔴" />
        </div>
      </div>

      <div className="card divide-y divide-slate-100">
        {visible.map((claim, i) => {
          const meta = FLAG_META[claim.flag];
          return (
            <div key={i} className="flex items-start gap-3 p-3">
              <span
                className={`mt-0.5 inline-flex h-6 min-w-6 items-center justify-center rounded-md px-1.5 text-xs font-bold ${meta.cls}`}
                title={meta.label}
              >
                {meta.icon}
              </span>
              <div className="flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] uppercase tracking-wide text-slate-500">
                    {claim.claim_type.replace(/_/g, " ")}
                  </span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${meta.cls}`}>
                    {meta.label}
                  </span>
                </div>
                <p className="mt-1 text-sm font-medium text-navy-900">“{claim.text}”</p>
                <p className="mt-1 text-sm text-slate-600">{claim.rationale}</p>

                {claim.required_evidence.length > 0 ? (
                  <p className="mt-1 text-xs text-slate-500">
                    <span className="font-semibold text-slate-600">Needs proof:</span>{" "}
                    {claim.required_evidence.join(" · ")}
                  </p>
                ) : (
                  <p className="mt-1 text-xs text-emerald-600">No additional proof needed.</p>
                )}

                {claim.compliant_rewrite && (
                  <div className="mt-2 rounded-md border-l-2 border-accent bg-accent/5 p-2">
                    <div className="flex items-center justify-between">
                      <div className="text-[10px] font-semibold uppercase tracking-wide text-accent-dark">
                        Compliant rewrite
                      </div>
                      <CopyButton text={claim.compliant_rewrite} />
                    </div>
                    <p className="mt-0.5 text-sm text-navy-900">{claim.compliant_rewrite}</p>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
