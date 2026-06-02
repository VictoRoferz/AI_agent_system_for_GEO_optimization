"use client";

import BrainPoints from "./BrainPoints";

// Small button that opens the per-block Syte AI agent. Carries the animated brain icon.
export default function AskAiButton({
  onClick,
  active = false,
  label = "Ask Syte AI engine",
  className = "",
}: {
  onClick: () => void;
  active?: boolean;
  label?: string;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition ${
        active
          ? "border-accent bg-accent/10 text-accent-dark"
          : "border-slate-300 text-slate-600 hover:border-accent hover:text-accent-dark"
      } ${className}`}
    >
      <BrainPoints size={14} className={active ? "text-accent-dark" : "text-accent"} />
      {label}
    </button>
  );
}
