"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import Report from "@/components/Report";
import { getRun, type AnalysisResult } from "@/lib/api";

export default function ResultsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getRun(id)
      .then((r) => {
        if (r.status === "error") setError(r.error || "Analysis failed");
        else setResult(r.result);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

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

  return <Report result={result} runId={id} />;
}
