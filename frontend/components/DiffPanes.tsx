"use client";

import { useEffect, useRef, useState } from "react";
import SnapshotFrame, { type Change } from "./SnapshotFrame";

// Two full-page frames (original + proposed) with optional scroll syncing. Each frame
// posts its scroll ratio to the parent; the parent relays it to the other frame.
export default function DiffPanes({
  html,
  changes,
  url,
}: {
  html: string;
  changes: Change[];
  url: string;
}) {
  const leftRef = useRef<HTMLIFrameElement>(null);
  const rightRef = useRef<HTMLIFrameElement>(null);
  const [sync, setSync] = useState(true);
  const syncRef = useRef(sync);
  syncRef.current = sync;

  useEffect(() => {
    function onMsg(e: MessageEvent) {
      if (!syncRef.current) return;
      const d = e.data as { geo?: string; ratio?: number };
      if (!d || d.geo !== "scroll") return;
      let target: HTMLIFrameElement | null = null;
      if (e.source === leftRef.current?.contentWindow) target = rightRef.current;
      else if (e.source === rightRef.current?.contentWindow) target = leftRef.current;
      target?.contentWindow?.postMessage({ geo: "scrollset", ratio: d.ratio }, "*");
    }
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h2 className="section-title">Original vs. proposed</h2>
        <div className="flex flex-wrap gap-3 text-[10px] uppercase tracking-wide text-slate-400">
          <span>
            <span className="mr-1 inline-block h-2 w-2 rounded-sm bg-yellow-300 align-middle" />
            will change
          </span>
          <span>
            <span className="mr-1 inline-block h-2 w-2 rounded-sm bg-emerald-300 align-middle" />
            proposed
          </span>
        </div>
        <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-xs text-slate-500">
          <input
            type="checkbox"
            checked={sync}
            onChange={(e) => setSync(e.target.checked)}
            className="accent-accent"
          />
          Sync scroll
        </label>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/70 px-4 py-2">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              Original page — click ▸ to preview a change
            </span>
            <a href={url} target="_blank" className="text-[11px] text-accent hover:underline">
              open ↗
            </a>
          </div>
          <div className="h-[640px]">
            <SnapshotFrame ref={leftRef} html={html} changes={changes} mode="original" />
          </div>
        </div>
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/70 px-4 py-2">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-accent-dark">
              Proposed page — changes applied
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
