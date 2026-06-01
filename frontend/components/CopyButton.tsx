"use client";

import { useState } from "react";

export default function CopyButton({
  text,
  className = "",
  label = "Copy",
}: {
  text: string;
  className?: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API unavailable (e.g. non-secure context) — fail silently.
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      className={`rounded-md border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-600 transition hover:border-accent hover:text-accent-dark ${className}`}
    >
      {copied ? "Copied ✓" : label}
    </button>
  );
}
