"use client";

import { forwardRef, useEffect, useMemo, useState } from "react";
import type { Claim } from "@/lib/api";

export interface Change {
  original: string;
  proposed: string;
  anchorId?: string | null;
  flags?: { quote: string; flag: "green" | "yellow" | "red"; note?: string }[];
}

// Cookie/consent overlays cover the snapshot and obscure content — remove them.
const OVERLAY_SELECTORS = [
  "#onetrust-consent-sdk",
  "#onetrust-banner-sdk",
  ".onetrust-pc-dark-filter",
  "#CybotCookiebotDialog",
  "#CybotCookiebotDialogBodyUnderlay",
  "#usercentrics-root",
  "#usercentrics-cmp-ui",
  "#didomi-host",
  "#cookie-law-info-bar",
  ".cli-modal-backdrop",
  '[class*="cookie-consent" i]',
  '[id*="cookie-consent" i]',
  '[class*="cookie-banner" i]',
  '[id*="cookie-banner" i]',
  '[aria-label*="cookie" i]',
];

const STYLE = `
html,body{overflow:auto!important;}
.geo-change-orig{background:#fde047!important;border-radius:2px;box-shadow:0 0 0 2px #facc15;scroll-margin-top:60px;}
.geo-change-orig.open{text-decoration:line-through;opacity:.55;}
.geo-arrow{cursor:pointer;border:none;background:#356f4f;color:#fff;border-radius:4px;
  font-size:11px;line-height:1;margin:0 4px;padding:2px 6px;vertical-align:middle;
  text-decoration:none!important;opacity:1!important;display:inline-block;}
.geo-arrow:hover{background:#2a5a40;}
.geo-new{background:#bbf7d0!important;color:#065f46!important;border-radius:2px;padding:0 3px;
  text-decoration:none!important;opacity:1!important;box-shadow:0 0 0 1px #34d399;}
.geo-flag-red{text-decoration:underline!important;text-decoration-style:dotted!important;text-decoration-color:#dc2626!important;text-decoration-thickness:2px!important;background:#fecaca!important;border-radius:2px;}
.geo-flag-yellow{text-decoration:underline!important;text-decoration-style:dotted!important;text-decoration-color:#d97706!important;text-decoration-thickness:2px!important;background:#fde68a!important;border-radius:2px;}
.geo-flag-green{text-decoration:underline!important;text-decoration-style:dotted!important;text-decoration-color:#059669!important;text-decoration-thickness:2px!important;}
.geo-change-orig .geo-new{display:none;}
.geo-change-orig.open .geo-new{display:inline;}
.geo-claim-red{border-left:4px solid #ef4444;background:#fef2f2;}
.geo-claim-yellow{border-left:4px solid #f59e0b;background:#fffbeb;}
.geo-claim-green{border-left:4px solid #10b981;background:#ecfdf5;}
.geo-claim-chip{margin-right:5px;font-size:.85em;}
html.geo-cv-red .geo-claim-yellow,html.geo-cv-red .geo-claim-green{border-left:none;background:transparent;}
html.geo-cv-red .geo-claim-yellow>.geo-claim-chip,html.geo-cv-red .geo-claim-green>.geo-claim-chip{display:none;}
html.geo-cv-off [class*="geo-claim-"]{border-left:none!important;background:transparent!important;}
html.geo-cv-off .geo-claim-chip{display:none;}
`;

// Reveal-on-click controller (original frame only): ▸ toggles the green proposal.
const CONTROLLER = `
document.addEventListener('click', function (e) {
  var b = e.target.closest('.geo-arrow');
  if (!b) return;
  e.preventDefault();
  var w = b.closest('.geo-change-orig');
  if (w) w.classList.toggle('open');
});
`;

// Claim-view controller (original frame): parent toggles which claim flags are shown.
const CLAIMVIEW = `
window.addEventListener('message', function (e) {
  var d = e.data; if (!d || d.geo !== 'claimview') return;
  var cl = document.documentElement.classList;
  cl.remove('geo-cv-red', 'geo-cv-off');
  if (d.mode === 'red') cl.add('geo-cv-red');
  else if (d.mode === 'off') cl.add('geo-cv-off');
});
`;

// Scroll-sync controller (both frames): report scroll ratio up, apply ratio from parent.
const SYNC = `
(function () {
  var lock = 0;
  function maxScroll() { var d = document.documentElement; return Math.max(0, (d.scrollHeight || 0) - (d.clientHeight || 0)); }
  window.addEventListener('scroll', function () {
    if (Date.now() < lock) return;
    var m = maxScroll();
    parent.postMessage({ geo: 'scroll', ratio: m ? window.scrollY / m : 0 }, '*');
  }, { passive: true });
  window.addEventListener('message', function (e) {
    var d = e.data; if (!d || d.geo !== 'scrollset') return;
    lock = Date.now() + 150;
    window.scrollTo(0, d.ratio * maxScroll());
  });
})();
`;

function normalize(s: string): string {
  return (s || "").replace(/\s+/g, " ").trim();
}

// Anchor first (exact data-geo-id), then fall back to tightest text match.
function findElement(doc: Document, ch: Change, used: Set<Element>): Element | null {
  if (ch.anchorId) {
    const el = doc.querySelector(`[data-geo-id="${ch.anchorId}"]`);
    if (el && !used.has(el)) return el;
  }
  const norm = normalize(ch.original);
  if (norm.length < 8) return null;
  const nodes = doc.body.querySelectorAll(
    "p,h1,h2,h3,h4,h5,h6,li,blockquote,figcaption,td,th,a,span,div"
  );
  let best: Element | null = null;
  nodes.forEach((el) => {
    if (used.has(el)) return;
    const t = normalize(el.textContent || "");
    if (t.length >= 8 && t.includes(norm)) {
      if (!best || (el.textContent || "").length < (best.textContent || "").length) best = el;
    }
  });
  return best;
}

const FLAG_EMOJI: Record<string, string> = { red: "🔴", yellow: "🟡", green: "🟢" };

// Append `text` to `parent`, wrapping each flagged substring (first non-overlapping match)
// in a <mark class="geo-flag-…"> so flagged statements/numbers show in the proposed pane.
function appendFlagged(doc: Document, parent: Element, text: string, flags: Change["flags"]) {
  const spans: { start: number; end: number; flag: string; note: string }[] = [];
  const taken: [number, number][] = [];
  for (const f of flags || []) {
    if (!f.quote) continue;
    let from = 0;
    while (from <= text.length) {
      const i = text.indexOf(f.quote, from);
      if (i < 0) break;
      const j = i + f.quote.length;
      if (!taken.some(([s, e]) => i < e && j > s)) {
        spans.push({ start: i, end: j, flag: f.flag, note: f.note || "" });
        taken.push([i, j]);
        break;
      }
      from = i + 1;
    }
  }
  spans.sort((a, b) => a.start - b.start);
  let cur = 0;
  for (const s of spans) {
    if (s.start > cur) parent.appendChild(doc.createTextNode(text.slice(cur, s.start)));
    const mark = doc.createElement("mark");
    mark.className = `geo-flag-${s.flag}`;
    if (s.note) mark.setAttribute("title", s.note);
    mark.textContent = text.slice(s.start, s.end);
    parent.appendChild(mark);
    cur = s.end;
  }
  if (cur < text.length) parent.appendChild(doc.createTextNode(text.slice(cur)));
}

function buildDoc(
  html: string,
  changes: Change[],
  mode: "original" | "proposed",
  claims: Claim[]
): string {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const head = doc.head || doc.documentElement;

  for (const sel of OVERLAY_SELECTORS) {
    try {
      doc.querySelectorAll(sel).forEach((el) => el.remove());
    } catch {
      /* invalid selector in some engines — ignore */
    }
  }

  const style = doc.createElement("style");
  style.textContent = STYLE;
  head.appendChild(style);

  if (doc.body) {
    const used = new Set<Element>();
    for (const ch of changes) {
      const el = findElement(doc, ch, used);
      if (!el) continue;
      used.add(el);

      if (mode === "proposed") {
        // Replace content with the proposed text; underline flagged statements/numbers inline.
        el.textContent = "";
        const span = doc.createElement("span");
        span.className = "geo-new";
        appendFlagged(doc, span, ch.proposed, ch.flags);
        el.appendChild(span);
      } else {
        el.classList.add("geo-change-orig");
        const arrow = doc.createElement("button");
        arrow.type = "button";
        arrow.className = "geo-arrow";
        arrow.textContent = "▸";
        arrow.title = "Show proposed change";
        const span = doc.createElement("span");
        span.className = "geo-new";
        appendFlagged(doc, span, ch.proposed, ch.flags);
        el.appendChild(arrow);
        el.appendChild(span);
      }
    }
  }

  // Claim/evidence flags overlay (both panes): color the anchored blocks.
  if (doc.body) {
    for (const c of claims) {
      if (!c.anchor_id) continue;
      const el = doc.querySelector(`[data-geo-id="${c.anchor_id}"]`);
      if (!el) continue;
      el.classList.add(`geo-claim-${c.flag}`);
      if (c.rationale) el.setAttribute("title", c.rationale);
      const chip = doc.createElement("span");
      chip.className = "geo-claim-chip";
      chip.textContent = FLAG_EMOJI[c.flag] || "•";
      el.insertBefore(chip, el.firstChild);
    }
  }

  const inject = (js: string) => {
    const s = doc.createElement("script");
    s.textContent = js;
    (doc.body || head).appendChild(s);
  };
  if (mode === "original") {
    inject(CONTROLLER);
    inject(CLAIMVIEW);
  }
  inject(SYNC);

  return "<!doctype html>" + doc.documentElement.outerHTML;
}

const SnapshotFrame = forwardRef<
  HTMLIFrameElement,
  { html: string; changes: Change[]; mode: "original" | "proposed"; claims?: Claim[] }
>(function SnapshotFrame({ html, changes, mode, claims = [] }, ref) {
  const [srcDoc, setSrcDoc] = useState<string | null>(null);
  const key = useMemo(
    () =>
      changes.map((c) => (c.anchorId || "") + c.original + "→" + c.proposed).join("|") +
      "::" +
      claims.map((c) => (c.anchor_id || "") + c.flag).join("|"),
    [changes, claims]
  );

  useEffect(() => {
    if (!html) {
      setSrcDoc("");
      return;
    }
    setSrcDoc(null);
    const t = setTimeout(() => setSrcDoc(buildDoc(html, changes, mode, claims)), 0);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [html, key, mode]);

  if (srcDoc === "")
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-slate-400">
        No snapshot was captured for this page. Re-run the analysis to generate one.
      </div>
    );

  if (srcDoc === null)
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-200 border-t-accent" />
      </div>
    );

  return (
    <iframe
      ref={ref}
      title={mode === "original" ? "Original page" : "Proposed page"}
      srcDoc={srcDoc}
      sandbox="allow-scripts"
      className="h-full w-full bg-white"
    />
  );
});

export default SnapshotFrame;
