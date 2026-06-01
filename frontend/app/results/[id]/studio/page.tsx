"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import CopyButton from "@/components/CopyButton";
import { ChangeView } from "@/components/Report";
import {
  PRIORITY_COLOR,
  generateRewrite,
  getRun,
  getStudio,
  sendChat,
  type ChatMessage,
  type PageRewrite,
  type Recommendation,
  type RewriteBlock,
} from "@/lib/api";

// --- one original→proposed content block (paired columns, GitHub-style) -----
function ContentRow({ block, flash }: { block: RewriteBlock; flash: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/70 px-4 py-2">
        <span className="text-sm font-medium text-navy-900">{block.label}</span>
        {block.changed ? (
          <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent-dark">
            changed
          </span>
        ) : (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] uppercase tracking-wide text-slate-400">
            kept
          </span>
        )}
      </div>
      <div className="grid gap-px bg-slate-100 lg:grid-cols-2">
        <div className="bg-white p-4">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Original</div>
          <p className="mt-1 whitespace-pre-wrap text-sm text-slate-500">
            {block.original || <span className="italic text-slate-300">— not present —</span>}
          </p>
        </div>
        <div
          className={`bg-white p-4 transition-colors duration-700 ${
            block.changed ? "border-l-2 border-accent" : ""
          } ${flash ? "bg-accent/10" : block.changed ? "bg-accent/[0.04]" : ""}`}
        >
          <div className="flex items-center justify-between">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-accent-dark">
              Proposed{block.changed ? " ✨" : ""}
            </div>
            {block.proposed && <CopyButton text={block.proposed} />}
          </div>
          <p className="mt-1 whitespace-pre-wrap text-sm text-navy-900">{block.proposed}</p>
          {block.changed && block.change_explanation && (
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="mt-2 text-[11px] font-medium text-accent-dark hover:underline"
            >
              {open ? "Hide why" : "Why this changed"}
            </button>
          )}
          {open && block.change_explanation && (
            <p className="mt-1 rounded-md bg-slate-50 p-2 text-xs text-slate-600">
              {block.change_explanation}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// --- one technical (code) change block --------------------------------------
function TechnicalRow({ block, flash }: { block: RewriteBlock; flash: boolean }) {
  return (
    <div
      className={`card p-4 transition-colors duration-700 ${flash ? "ring-2 ring-accent" : ""}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-navy-900">{block.label}</span>
        <CopyButton text={block.proposed} className="border-slate-600 bg-navy-800 text-slate-200" />
      </div>
      <pre className="mt-2 overflow-x-auto rounded-md bg-navy-900 p-3 text-xs leading-relaxed text-slate-100">
        <code>{block.proposed}</code>
      </pre>
      {block.change_explanation && (
        <p className="mt-2 text-xs text-slate-600">{block.change_explanation}</p>
      )}
      {block.original && (
        <details className="mt-2 text-xs text-slate-500">
          <summary className="cursor-pointer">Current markup</summary>
          <pre className="mt-1 overflow-x-auto rounded-md bg-slate-100 p-2 text-[11px] text-slate-600">
            <code>{block.original}</code>
          </pre>
        </details>
      )}
    </div>
  );
}

export default function StudioPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [url, setUrl] = useState("");
  const [rewrite, setRewrite] = useState<PageRewrite | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [suggestions, setSuggestions] = useState<Recommendation[]>([]);
  const [flashIds, setFlashIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Load run + studio state; generate the rewrite on first visit.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const run = await getRun(id);
        if (cancelled) return;
        if (run.status === "error" || !run.result) {
          setError(run.error || "This run has no result to work from.");
          return;
        }
        setUrl(run.result.url);
        const state = await getStudio(id);
        if (cancelled) return;
        setMessages(state.chat_history || []);
        setSuggestions(state.extra_recommendations || []);
        if (state.rewrite) {
          setRewrite(state.rewrite);
        } else {
          setGenerating(true);
          const fresh = await generateRewrite(id);
          if (!cancelled) setRewrite(fresh);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) {
          setLoading(false);
          setGenerating(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  function flash(ids: string[]) {
    if (!ids.length) return;
    setFlashIds(new Set(ids));
    setTimeout(() => setFlashIds(new Set()), 1600);
  }

  async function regenerate() {
    setGenerating(true);
    setError(null);
    try {
      const fresh = await generateRewrite(id, true);
      setRewrite(fresh);
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerating(false);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const message = input.trim();
    if (!message || sending) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: message }]);
    setSending(true);
    try {
      const res = await sendChat(id, message);
      setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
      if (res.rewrite) {
        setRewrite(res.rewrite);
        // Flash blocks the agent touched (resolve "new" → newest block ids client-side).
        const editedReal = res.edited_block_ids.filter((b) => b !== "new");
        flash(editedReal);
      }
      if (res.new_recommendations.length) setSuggestions(res.new_recommendations);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `⚠️ ${String(e)}` },
      ]);
    } finally {
      setSending(false);
    }
  }

  if (loading || generating)
    return (
      <div className="card flex flex-col items-center gap-3 p-10 text-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-accent" />
        <p className="text-sm text-slate-600">
          {generating ? "The agent is rewriting the page…" : "Loading studio…"}
        </p>
        <p className="text-xs text-slate-400">This can take a moment for a full rewrite.</p>
      </div>
    );

  if (error)
    return (
      <div className="card p-6">
        <h2 className="font-semibold text-priority-p0">Studio unavailable</h2>
        <p className="mt-2 text-sm text-slate-600">{error}</p>
        <Link href={`/results/${id}`} className="mt-4 inline-block text-accent hover:underline">
          ← Back to report
        </Link>
      </div>
    );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-navy-900">AI Studio</h1>
            <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent-dark">
              proposed rewrite
            </span>
          </div>
          <a href={url} target="_blank" className="text-sm text-accent hover:underline">
            {url}
          </a>
        </div>
        <div className="flex gap-2">
          <button
            onClick={regenerate}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm hover:border-slate-400"
          >
            ↻ Regenerate
          </button>
          <Link
            href={`/results/${id}`}
            className="rounded-lg bg-navy-800 px-4 py-2 text-sm text-white hover:bg-navy-900"
          >
            ← Back to report
          </Link>
        </div>
      </div>

      {rewrite?.summary && (
        <div className="card border-l-4 border-accent p-4">
          <div className="section-title">What the agent changed</div>
          <p className="mt-1 text-sm leading-relaxed text-slate-700">{rewrite.summary}</p>
        </div>
      )}

      {/* Content rewrite — two panes */}
      <div>
        <div className="mb-2 flex items-center gap-3">
          <h2 className="section-title">Content rewrite</h2>
          <div className="flex gap-3 text-[10px] uppercase tracking-wide text-slate-400">
            <span>← Original</span>
            <span className="text-accent-dark">Proposed →</span>
          </div>
        </div>
        <div className="space-y-3">
          {rewrite?.content_blocks.map((b) => (
            <ContentRow key={b.id} block={b} flash={flashIds.has(b.id)} />
          ))}
          {!rewrite?.content_blocks.length && (
            <p className="text-sm text-slate-400">No content blocks were produced.</p>
          )}
        </div>
      </div>

      {/* Technical changes */}
      {rewrite && rewrite.technical_blocks.length > 0 && (
        <div>
          <h2 className="section-title mb-2">Technical changes</h2>
          <div className="space-y-3">
            {rewrite.technical_blocks.map((b) => (
              <TechnicalRow key={b.id} block={b} flash={flashIds.has(b.id)} />
            ))}
          </div>
        </div>
      )}

      {/* Agent suggestions (new recommendations from chat) */}
      {suggestions.length > 0 && (
        <div>
          <h2 className="section-title mb-2">Agent suggestions ({suggestions.length})</h2>
          <div className="space-y-2">
            {suggestions.map((s) => (
              <div key={s.id} className="card p-4">
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-flex h-6 min-w-6 items-center justify-center rounded px-1.5 text-[11px] font-bold text-white ${PRIORITY_COLOR[s.priority]}`}
                  >
                    {s.priority}
                  </span>
                  <h4 className="font-semibold text-navy-900">{s.title}</h4>
                </div>
                <p className="mt-1 text-sm text-slate-600">{s.description}</p>
                {s.change && <ChangeView change={s.change} />}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Chat */}
      <div className="card flex flex-col">
        <div className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-navy-900">Ask the GEO agent</h2>
          <p className="text-xs text-slate-400">
            Ask about the page, its AI-search visibility, or tell the agent to rewrite a part —
            it updates the proposed side live.
          </p>
        </div>
        <div className="max-h-96 space-y-3 overflow-y-auto px-4 py-4">
          {messages.length === 0 && (
            <div className="space-y-2 text-sm text-slate-400">
              <p>Try:</p>
              <ul className="list-disc pl-5">
                <li>“Why would ChatGPT cite this page or not?”</li>
                <li>“Rewrite the intro to answer the query in the first sentence.”</li>
                <li>“Suggest one more high-impact recommendation.”</li>
              </ul>
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${
                  m.role === "user"
                    ? "bg-navy-800 text-white"
                    : "bg-slate-100 text-slate-800"
                }`}
              >
                {m.content}
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="rounded-2xl bg-slate-100 px-3 py-2 text-sm text-slate-400">
                thinking…
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>
        <form onSubmit={submit} className="flex gap-2 border-t border-slate-100 p-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question or request a change…"
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-accent"
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-accent-dark disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
