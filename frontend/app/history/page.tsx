"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { engineLabel, listRuns, type RunSummary } from "@/lib/api";

export default function HistoryPage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listRuns()
      .then(setRuns)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-navy-900">Analysis history</h1>
      {loading ? (
        <p className="text-slate-500">Loading…</p>
      ) : runs.length === 0 ? (
        <div className="card p-6 text-slate-500">
          No analyses yet.{" "}
          <Link href="/" className="text-accent hover:underline">
            Run your first one →
          </Link>
        </div>
      ) : (
        <div className="card divide-y divide-slate-100">
          {runs.map((r) => (
            <Link
              key={r.id}
              href={`/results/${r.id}`}
              className="flex items-center justify-between gap-4 px-5 py-3 hover:bg-slate-50"
            >
              <div className="min-w-0">
                <div className="truncate font-medium text-navy-900">{r.url}</div>
                <div className="text-xs text-slate-400">
                  {new Date(r.created_at).toLocaleString()} · {r.mode} · {r.model_key}
                  {r.status === "error" && (
                    <span className="ml-2 text-priority-p0">failed</span>
                  )}
                </div>
              </div>
              {r.overall_score != null && (
                <span className="rounded-full bg-navy-50 px-3 py-1 text-sm font-semibold text-navy-700">
                  {r.overall_score}
                </span>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
