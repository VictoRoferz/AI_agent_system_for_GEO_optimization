"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getModels,
  getOptions,
  runAnalysis,
  type ModelOption,
  type Option,
} from "@/lib/api";
import { useAgentStream } from "@/lib/useAgentStream";
import AgentTimeline from "@/components/AgentTimeline";

export default function NewAnalysisPage() {
  const router = useRouter();
  const [modes, setModes] = useState<Option[]>([]);
  const [engines, setEngines] = useState<Option[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);

  const [url, setUrl] = useState("");
  const [queries, setQueries] = useState<string[]>([""]);
  const [mode, setMode] = useState("geo_factors");
  const [selectedEngines, setSelectedEngines] = useState<string[]>(["chatgpt", "ai_overviews"]);
  const [modelKey, setModelKey] = useState("claude-default");
  const [file, setFile] = useState<File | null>(null);

  const [running, setRunning] = useState(false);
  const [autoOptimize, setAutoOptimize] = useState(false);
  const [optimizeDepth, setOptimizeDepth] = useState<"quick" | "full">("quick");
  const stream = useAgentStream();

  useEffect(() => {
    getOptions().then((o) => {
      setModes(o.modes);
      setEngines(o.target_engines);
    });
    getModels().then((m) => {
      setModels(m.models);
      setModelKey(m.default);
    });
  }, []);

  function updateQuery(i: number, v: string) {
    setQueries((q) => q.map((x, idx) => (idx === i ? v : x)));
  }
  function toggleEngine(key: string) {
    setSelectedEngines((e) =>
      e.includes(key) ? e.filter((x) => x !== key) : [...e, key]
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setRunning(true);
    stream.begin();
    stream.ingestProgress({ step: "start", message: "Starting…", pct: 2 });

    const form = new FormData();
    form.append("url", url);
    form.append("queries", JSON.stringify(queries.filter((q) => q.trim())));
    form.append("mode", mode);
    form.append("target_engines", JSON.stringify(selectedEngines));
    form.append("model_key", modelKey);
    if (file) form.append("goals_file", file);

    try {
      await runAnalysis(form, {
        onProgress: stream.ingestProgress,
        onAgentEvent: stream.ingest,
        onResult: (r) => {
          stream.finish();
          router.push(
            autoOptimize
              ? `/results/${r.run_id}/studio?optimize=1&depth=${optimizeDepth}`
              : `/results/${r.run_id}`
          );
        },
        onError: (msg) => {
          stream.finish(msg);
          setRunning(false);
        },
      });
    } catch (err) {
      stream.finish(String(err));
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-navy-900">New GEO Analysis</h1>
        <p className="text-slate-500 mt-1">
          Analyze a page&apos;s readiness to be cited by AI search engines and its alignment with
          your strategic goals.
        </p>
      </div>

      <form onSubmit={submit} className="card p-6 space-y-6">
        {/* URL */}
        <div>
          <label className="section-title">Page URL</label>
          <input
            type="url"
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/article"
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-accent focus:outline-none"
          />
        </div>

        {/* Queries */}
        <div>
          <label className="section-title">Queries</label>
          <div className="mt-1 space-y-2">
            {queries.map((q, i) => (
              <div key={i} className="flex gap-2">
                <input
                  value={q}
                  onChange={(e) => updateQuery(i, e.target.value)}
                  placeholder={`Query ${i + 1} — e.g. "best running shoes for flat feet"`}
                  className="flex-1 rounded-lg border border-slate-300 px-3 py-2 focus:border-accent focus:outline-none"
                />
                {queries.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setQueries((qs) => qs.filter((_, idx) => idx !== i))}
                    className="px-3 text-slate-400 hover:text-priority-p0"
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
            <button
              type="button"
              onClick={() => setQueries((q) => [...q, ""])}
              className="text-sm text-accent hover:text-accent-dark"
            >
              + Add query
            </button>
          </div>
        </div>

        {/* Strategic goals upload */}
        <div>
          <label className="section-title">Strategic goals document (PDF / Word)</label>
          <input
            type="file"
            accept=".pdf,.doc,.docx,.txt,.md"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="mt-1 block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-navy-700 file:px-4 file:py-2 file:text-white hover:file:bg-navy-800"
          />
        </div>

        {/* Mode (single-select) */}
        <div>
          <label className="section-title">Analysis mode</label>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {modes.map((m) => (
              <button
                type="button"
                key={m.key}
                onClick={() => setMode(m.key)}
                className={`rounded-lg border px-4 py-3 text-left text-sm ${
                  mode === m.key
                    ? "border-accent bg-accent/5 ring-1 ring-accent"
                    : "border-slate-300 hover:border-slate-400"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {/* Target engines (multi-select) + model picker */}
        <div className="grid gap-6 sm:grid-cols-2">
          <div>
            <label className="section-title">Target AI engines</label>
            <div className="mt-2 flex flex-wrap gap-2">
              {engines.map((en) => (
                <button
                  type="button"
                  key={en.key}
                  onClick={() => toggleEngine(en.key)}
                  className={`rounded-full border px-3 py-1.5 text-sm ${
                    selectedEngines.includes(en.key)
                      ? "border-accent bg-accent text-white"
                      : "border-slate-300 text-slate-600 hover:border-slate-400"
                  }`}
                >
                  {en.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="section-title">Analysis model</label>
            <select
              value={modelKey}
              onChange={(e) => setModelKey(e.target.value)}
              className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-accent focus:outline-none"
            >
              {models.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label} {m.configured ? "" : "(no key)"}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Continue straight into the optimization agent after the analysis */}
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={autoOptimize}
              onChange={(e) => setAutoOptimize(e.target.checked)}
              className="h-4 w-4 accent-[#356f4f]"
            />
            Continue into optimization (the agent rewrites the whole page after the analysis)
          </label>
          {autoOptimize && (
            <div className="flex gap-1.5">
              {(["quick", "full"] as const).map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setOptimizeDepth(d)}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    optimizeDepth === d
                      ? "border-accent bg-accent text-white"
                      : "border-slate-300 text-slate-600 hover:border-slate-400"
                  }`}
                >
                  {d === "quick" ? "Quick pass" : "Full depth"}
                </button>
              ))}
            </div>
          )}
        </div>

        {stream.status !== "idle" && (
          <AgentTimeline
            phases={stream.phases}
            status={stream.status}
            error={stream.error}
            progressPct={stream.progress?.pct ?? null}
            startedAt={stream.startedAt}
            finishedAt={stream.finishedAt}
            title="Agent activity"
            maxHeightClass="max-h-72"
          />
        )}

        <button
          type="submit"
          disabled={running || !url}
          className="rounded-lg bg-navy-800 px-6 py-2.5 font-medium text-white hover:bg-navy-900 disabled:opacity-50"
        >
          {running ? "Analyzing…" : "Run analysis"}
        </button>
      </form>
    </div>
  );
}
