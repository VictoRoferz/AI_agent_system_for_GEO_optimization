"use client";

// Hero card that starts an optimization run: depth choice (cheap test vs full
// depth), optional strategic-goals re-upload (goals text isn't persisted with
// runs), and a phase explainer so users know what the agent will do.

import { useState } from "react";
import BrainPoints from "@/components/BrainPoints";

const PHASES = [
  ["Plan", "decides what to change on every block and sets one voice"],
  ["Audit", "an expert panel checks the page against every KB factor"],
  ["Rewrite", "rewrites all content + technical elements, with a why per change"],
  ["Verify", "self-checks compliance, fidelity and coverage"],
] as const;

export default function OptimizeLauncher({
  onStart,
  regenerate = false,
  busy = false,
  initialDepth = "quick",
}: {
  onStart: (depth: "quick" | "full", goalsFile: File | null) => void;
  regenerate?: boolean;
  busy?: boolean;
  initialDepth?: "quick" | "full";
}) {
  const [depth, setDepth] = useState<"quick" | "full">(initialDepth);
  const [goalsFile, setGoalsFile] = useState<File | null>(null);

  return (
    <div className="card p-8">
      <div className="flex items-start gap-4">
        <div className="rounded-xl bg-accent/10 p-3">
          <BrainPoints size={34} className="text-accent" />
        </div>
        <div className="flex-1">
          <h2 className="text-lg font-bold text-navy-900">
            {regenerate ? "Re-run the optimization agent" : "Let the agent optimize this page"}
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            The agent does the whole job and explains every change it makes:
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {PHASES.map(([name, desc]) => (
              <div key={name} className="flex items-start gap-2 text-xs text-slate-600">
                <span className="mt-0.5 font-semibold text-accent-dark">{name}</span>
                <span>{desc}</span>
              </div>
            ))}
          </div>

          <div className="mt-5">
            <div className="section-title">Depth</div>
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                onClick={() => setDepth("quick")}
                className={`rounded-lg border px-4 py-2 text-left text-sm ${
                  depth === "quick"
                    ? "border-accent bg-accent/5 ring-1 ring-accent"
                    : "border-slate-300 hover:border-slate-400"
                }`}
              >
                <span className="font-medium text-navy-900">Quick pass</span>
                <span className="block text-xs text-slate-500">
                  ~7-8 AI calls · 1 rewrite option per block · fastest & cheapest
                </span>
              </button>
              <button
                type="button"
                onClick={() => setDepth("full")}
                className={`rounded-lg border px-4 py-2 text-left text-sm ${
                  depth === "full"
                    ? "border-accent bg-accent/5 ring-1 ring-accent"
                    : "border-slate-300 hover:border-slate-400"
                }`}
              >
                <span className="font-medium text-navy-900">Full depth</span>
                <span className="block text-xs text-slate-500">
                  ~15-18 AI calls · 3 options per block · expert verification loop
                </span>
              </button>
            </div>
          </div>

          <div className="mt-4">
            <div className="section-title">Strategic goals document (optional)</div>
            <input
              type="file"
              accept=".pdf,.doc,.docx,.txt,.md"
              onChange={(e) => setGoalsFile(e.target.files?.[0] || null)}
              className="mt-1 block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-navy-700 file:px-4 file:py-2 file:text-white hover:file:bg-navy-800"
            />
            <p className="mt-1 text-[11px] text-slate-400">
              Goals aren&apos;t stored with the run — re-attach the document to let it guide the rewrite.
            </p>
          </div>

          {regenerate && (
            <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              Re-running replaces the current proposed rewrite, including manual edits made in
              the studio.
            </p>
          )}

          <button
            type="button"
            disabled={busy}
            onClick={() => onStart(depth, goalsFile)}
            className="mt-5 inline-flex items-center gap-2 rounded-lg bg-accent px-6 py-2.5 font-medium text-white hover:bg-accent-dark disabled:opacity-50"
          >
            <BrainPoints size={16} color="white" />
            {busy ? "Starting…" : "Start optimization"}
          </button>
        </div>
      </div>
    </div>
  );
}
