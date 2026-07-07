"use client";

// Chip showing a rewrite block's self-verification outcome (agent runs).

import type { VerificationStatus } from "@/lib/api";

const VERIFY_META: Record<
  Exclude<VerificationStatus, "unverified">,
  { glyph: string; label: string; cls: string }
> = {
  passed: { glyph: "✓", label: "Verified", cls: "bg-emerald-100 text-emerald-700" },
  revised: { glyph: "⚠", label: "Revised after check", cls: "bg-amber-100 text-amber-700" },
  needs_human: { glyph: "✗", label: "Flagged for review", cls: "bg-rose-100 text-rose-700" },
};

export default function VerificationBadge({
  status,
  compact = false,
  title,
}: {
  status?: VerificationStatus | null;
  compact?: boolean;
  title?: string;
}) {
  if (!status || status === "unverified") return null;
  const meta = VERIFY_META[status];
  return (
    <span
      title={title || meta.label}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${meta.cls}`}
    >
      <span aria-hidden>{meta.glyph}</span>
      {!compact && meta.label}
    </span>
  );
}
