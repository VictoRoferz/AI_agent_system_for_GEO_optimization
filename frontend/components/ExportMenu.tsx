"use client";

// Export the agent's output: deployable HTML (primary), markdown change
// package, and a copy-to-clipboard convenience for CMS paste.

import { useState } from "react";
import { changePackageUrl, fetchOptimizedHtml, optimizedPageUrl } from "@/lib/api";

export default function ExportMenu({ runId }: { runId: string }) {
  const [copied, setCopied] = useState(false);
  const [copying, setCopying] = useState(false);

  async function copyHtml() {
    setCopying(true);
    try {
      const html = await fetchOptimizedHtml(runId);
      await navigator.clipboard.writeText(html);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — the download buttons still work */
    } finally {
      setCopying(false);
    }
  }

  return (
    <div className="flex flex-wrap gap-2">
      <a
        href={optimizedPageUrl(runId)}
        download
        className="rounded-lg bg-navy-800 px-4 py-2 text-sm text-white hover:bg-navy-900"
      >
        ⬇ Optimized page (HTML)
      </a>
      <a
        href={changePackageUrl(runId)}
        className="rounded-lg border border-slate-300 px-4 py-2 text-sm hover:border-slate-400"
      >
        Change package (MD)
      </a>
      <button
        type="button"
        onClick={copyHtml}
        disabled={copying}
        className="rounded-lg border border-slate-300 px-4 py-2 text-sm hover:border-slate-400 disabled:opacity-50"
      >
        {copied ? "Copied ✓" : copying ? "Copying…" : "Copy HTML"}
      </button>
    </div>
  );
}
