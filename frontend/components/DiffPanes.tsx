"use client";

import { useEffect, useRef, useState } from "react";
import SnapshotFrame, { type Change } from "./SnapshotFrame";
import type { Claim, ClaimFlag } from "@/lib/api";

type ClaimView = "all" | "red" | "off";

// Two full-page frames (original + proposed) with optional scroll syncing. Each frame
// posts its scroll ratio to the parent; the parent relays it to the other frame.
// The original frame also overlays 🟢/🟡/🔴 claim flags, controlled here via postMessage.
export default function DiffPanes({
  html,
  changes,
  claims = [],
  url,
  onWhy,
}: {
  html: string;
  changes: Change[];
  claims?: Claim[];
  url: string;
  onWhy?: (blockId: string) => void;
}) {
  const leftRef = useRef<HTMLIFrameElement>(null);
  const rightRef = useRef<HTMLIFrameElement>(null);
  const [sync, setSync] = useState(true);
  const [claimView, setClaimView] = useState<ClaimView>("all");
  const syncRef = useRef(sync);
  syncRef.current = sync;
  const onWhyRef = useRef(onWhy);
  onWhyRef.current = onWhy;

  useEffect(() => {
    function onMsg(e: MessageEvent) {
      const d = e.data as { geo?: string; ratio?: number; blockId?: string };
      if (!d) return;
      if (d.geo === "why" && d.blockId) {
        onWhyRef.current?.(d.blockId);
        return;
      }
      if (!syncRef.current || d.geo !== "scroll") return;
      let target: HTMLIFrameElement | null = null;
      if (e.source === leftRef.current?.contentWindow) target = rightRef.current;
      else if (e.source === rightRef.current?.contentWindow) target = leftRef.current;
      target?.contentWindow?.postMessage({ geo: "scrollset", ratio: d.ratio }, "*");
    }
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  // Push the claim-view mode into the (sandboxed) proposed frame — flags live there.
  useEffect(() => {
    rightRef.current?.contentWindow?.postMessage({ geo: "claimview", mode: claimView }, "*");
  }, [claimView, claims]);

  const counts = claims.reduce(
    (acc, c) => ((acc[c.flag] = (acc[c.flag] || 0) + 1), acc),
    {} as Record<ClaimFlag, number>
  );
  const hasClaims = claims.length > 0;

  const CvBtn = ({ mode, label }: { mode: ClaimView; label: string }) => (
    <button
      type="button"
      onClick={() => setClaimView(mode)}
      className={`rounded-full px-2 py-0.5 text-[10px] font-medium transition ${
        claimView === mode ? "bg-navy-800 text-white" : "bg-slate-100 text-slate-500 hover:bg-slate-200"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h2 className="section-title">Original vs. proposed</h2>
        <div className="flex flex-wrap gap-3 text-[10px] uppercase tracking-wide text-slate-400">
          <span>
            <span className="mr-1 inline-block h-2 w-2 rounded-sm bg-blue-500 align-middle" />
            optimized
          </span>
          {hasClaims && (
            <span className="text-slate-400">
              · evidence (right)&nbsp;
              <span className="text-rose-500">🔴 {counts.red || 0}</span>{" "}
              <span className="text-amber-500">🟡 {counts.yellow || 0}</span>{" "}
              <span className="text-emerald-500">🟢 {counts.green || 0}</span>
            </span>
          )}
        </div>
        <div className="ml-auto flex items-center gap-3">
          {hasClaims && (
            <div className="flex items-center gap-1">
              <span className="text-[10px] uppercase tracking-wide text-slate-400">Flags</span>
              <CvBtn mode="all" label="All" />
              <CvBtn mode="red" label="Only 🔴" />
              <CvBtn mode="off" label="Off" />
            </div>
          )}
          <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-500">
            <input
              type="checkbox"
              checked={sync}
              onChange={(e) => setSync(e.target.checked)}
              className="accent-accent"
            />
            Sync scroll
          </label>
        </div>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/70 px-4 py-2">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              Original page — ▸ preview an optimization
            </span>
            <a href={url} target="_blank" className="text-[11px] text-accent hover:underline">
              open ↗
            </a>
          </div>
          <div className="h-[640px]">
            <SnapshotFrame ref={leftRef} html={html} changes={changes} claims={claims} mode="original" />
          </div>
        </div>
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/70 px-4 py-2">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-blue-700">
              Proposed page — optimized + evidence flags
            </span>
          </div>
          <div className="h-[640px]">
            <SnapshotFrame ref={rightRef} html={html} changes={changes} mode="proposed" />
          </div>
        </div>
      </div>
    </div>
  );
}
