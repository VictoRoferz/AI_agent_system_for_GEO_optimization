"use client";

import { useEffect, useRef, useState } from "react";
import BrainPoints from "./BrainPoints";
import {
  sendChat,
  type ChatMessage,
  type PageRewrite,
  type Recommendation,
} from "@/lib/api";

type Size = "min" | "normal" | "expanded";

// The Syte AI agent panel. Reused page-wide (blockId=null) and per content block
// (blockId set). Supports attach-any-document, and minimize/normal/expanded sizing.
export default function ChatAgent({
  runId,
  blockId = null,
  variant = "panel",
  title = "Syte AI engine",
  subtitle,
  placeholder = "Ask the agent, or attach a document…",
  initialMessages = [],
  onRewrite,
  onEditedBlocks,
  onNewRecommendations,
}: {
  runId: string;
  blockId?: string | null;
  variant?: "panel" | "inline";
  title?: string;
  subtitle?: string;
  placeholder?: string;
  initialMessages?: ChatMessage[];
  onRewrite?: (r: PageRewrite) => void;
  onEditedBlocks?: (ids: string[]) => void;
  onNewRecommendations?: (recs: Recommendation[]) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [sending, setSending] = useState(false);
  const [size, setSize] = useState<Size>("normal");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messages.length || sending)
      endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, sending]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const msg = input.trim();
    if ((!msg && !file) || sending) return;
    const attached = file;
    const shown = (msg || `Use the attached document`) + (attached ? `  📎 ${attached.name}` : "");
    setInput("");
    setFile(null);
    setMessages((m) => [...m, { role: "user", content: shown }]);
    setSending(true);
    try {
      const res = await sendChat(runId, {
        message: msg || "Use the attached document to improve this.",
        blockId,
        file: attached,
      });
      setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
      if (res.rewrite) onRewrite?.(res.rewrite);
      if (res.edited_block_ids?.length) onEditedBlocks?.(res.edited_block_ids);
      if (res.new_recommendations?.length) onNewRecommendations?.(res.new_recommendations);
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", content: `⚠️ ${String(err)}` }]);
    } finally {
      setSending(false);
    }
  }

  const isInline = variant === "inline";
  const bodyHeight = isInline ? "max-h-56" : size === "expanded" ? "h-[32rem]" : "h-72";
  const open = size !== "min";

  return (
    <div className="card flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/70 px-3 py-2">
        <div className="flex items-center gap-2">
          <BrainPoints size={16} className="text-accent" />
          <div className="leading-tight">
            <div className="text-sm font-semibold text-navy-900">{title}</div>
            {subtitle && <div className="text-[11px] text-slate-400">{subtitle}</div>}
          </div>
        </div>
        {!isInline && (
          <div className="flex items-center gap-1 text-slate-400">
            <button
              type="button"
              title={size === "expanded" ? "Shrink" : "Expand"}
              onClick={() => setSize(size === "expanded" ? "normal" : "expanded")}
              className="rounded px-1.5 py-0.5 text-xs hover:bg-slate-200 hover:text-slate-600"
            >
              {size === "expanded" ? "⤡" : "⤢"}
            </button>
            <button
              type="button"
              title={open ? "Minimize" : "Open"}
              onClick={() => setSize(open ? "min" : "normal")}
              className="rounded px-1.5 py-0.5 text-xs hover:bg-slate-200 hover:text-slate-600"
            >
              {open ? "—" : "▢"}
            </button>
          </div>
        )}
      </div>

      {open && (
        <>
          <div className={`space-y-3 overflow-y-auto px-3 py-3 ${bodyHeight}`}>
            {messages.length === 0 && (
              <p className="text-xs text-slate-400">
                Ask for alternatives, attach a study/brief/any document, or say “embed these
                findings and rewrite”.
              </p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${
                    m.role === "user" ? "bg-navy-800 text-white" : "bg-slate-100 text-slate-800"
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <BrainPoints size={18} className="text-accent" />
                thinking…
              </div>
            )}
            <div ref={endRef} />
          </div>

          <form onSubmit={submit} className="border-t border-slate-100 p-2">
            {file && (
              <div className="mb-2 flex items-center gap-2 rounded-md bg-accent/10 px-2 py-1 text-[11px] text-accent-dark">
                📎 {file.name}
                <button type="button" onClick={() => setFile(null)} className="ml-auto hover:text-rose-500">
                  ✕
                </button>
              </div>
            )}
            <div className="flex items-center gap-2">
              <label
                title="Attach a document (PDF, Word, txt…)"
                className="cursor-pointer rounded-lg border border-slate-300 px-2 py-2 text-slate-500 hover:border-accent hover:text-accent-dark"
              >
                📎
                <input
                  type="file"
                  accept=".pdf,.doc,.docx,.txt,.md"
                  className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
              </label>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={placeholder}
                className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-accent"
              />
              <button
                type="submit"
                disabled={sending || (!input.trim() && !file)}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-accent-dark disabled:opacity-50"
              >
                Send
              </button>
            </div>
          </form>
        </>
      )}
    </div>
  );
}
