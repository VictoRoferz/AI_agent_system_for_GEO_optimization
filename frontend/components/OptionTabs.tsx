"use client";

const STYLE_LABELS = ["Conservative", "Balanced", "Punchy"];

// Tabs to switch a content block between its 3 rewrite options (distinct styles).
export default function OptionTabs({
  count,
  selected,
  busy = false,
  onSelect,
}: {
  count: number;
  selected: number;
  busy?: boolean;
  onSelect: (index: number) => void;
}) {
  if (count <= 1) return null;
  return (
    <div className="flex flex-wrap items-center gap-1">
      <span className="mr-1 text-[10px] uppercase tracking-wide text-slate-400">Option</span>
      {Array.from({ length: count }).map((_, i) => (
        <button
          key={i}
          type="button"
          disabled={busy}
          onClick={() => onSelect(i)}
          title={STYLE_LABELS[i] || `Option ${i + 1}`}
          className={`rounded-full px-2 py-0.5 text-[10px] font-medium transition disabled:opacity-50 ${
            i === selected
              ? "bg-accent text-white"
              : "bg-slate-100 text-slate-500 hover:bg-slate-200"
          }`}
        >
          {i + 1}
          {STYLE_LABELS[i] ? ` · ${STYLE_LABELS[i]}` : ""}
        </button>
      ))}
    </div>
  );
}
