"use client";

import type { PageSignals, PageRewrite, RewriteBlock } from "@/lib/api";

// ---------- heading outline ------------------------------------------------
interface Heading {
  level: number;
  text: string;
  state?: "changed" | "new";
}

function parseHeadings(headings: string[]): Heading[] {
  return headings.map((h) => {
    const m = h.match(/^h([1-6]):\s*(.*)$/i);
    return m ? { level: Number(m[1]), text: m[2] } : { level: 2, text: h };
  });
}

const norm = (s: string) => (s || "").replace(/\s+/g, " ").trim().toLowerCase();

function proposedHeadings(original: Heading[], blocks: RewriteBlock[]): Heading[] {
  const headingBlocks = blocks.filter(
    (b) => (b.kind === "heading" || b.kind === "title") && b.changed
  );
  const out: Heading[] = original.map((h) => ({ ...h }));
  const news: Heading[] = [];
  for (const b of headingBlocks) {
    if (b.original.trim()) {
      const hit = out.find((h) => norm(h.text).includes(norm(b.original)) && !h.state);
      if (hit) {
        hit.text = b.proposed;
        hit.state = "changed";
        continue;
      }
    }
    news.push({ level: b.kind === "title" ? 1 : 2, text: b.proposed, state: "new" });
  }
  return [...out, ...news];
}

function Outline({ items }: { items: Heading[] }) {
  if (!items.length) return <p className="text-xs italic text-slate-400">No headings detected.</p>;
  return (
    <ul className="space-y-1 text-sm">
      {items.map((h, i) => (
        <li key={i} style={{ paddingLeft: (h.level - 1) * 14 }}>
          <span className="mr-1 rounded bg-slate-100 px-1 text-[10px] font-semibold text-slate-500">
            H{h.level}
          </span>
          <span
            className={
              h.state === "new"
                ? "rounded-sm bg-emerald-100 px-1 text-emerald-800"
                : h.state === "changed"
                ? "rounded-sm bg-yellow-200 px-1 text-yellow-900"
                : "text-slate-700"
            }
          >
            {h.text}
          </span>
        </li>
      ))}
    </ul>
  );
}

// ---------- meta / schema map ----------------------------------------------
interface MetaRow {
  label: string;
  original: string;
  present: boolean;
  proposed: string;
  proposedState: "kept" | "added" | "updated";
}

const test = (b: RewriteBlock, re: RegExp) => re.test(b.proposed) || re.test(b.label);

function buildMetaRows(s: PageSignals, rw: PageRewrite): MetaRow[] {
  const tech = rw.technical_blocks;
  const content = rw.content_blocks;
  const find = (re: RegExp) => tech.find((b) => test(b, re));

  const titleBlock = content.find((b) => b.kind === "title" && b.changed);
  const descBlock =
    content.find((b) => /meta\s*description/i.test(b.label) && b.changed) ||
    find(/name=["']description|meta\s*description/i);
  const canonicalBlock = find(/rel=["']canonical|canonical/i);
  const jsonldBlock = tech.find(
    (b) => b.kind === "jsonld" || /ld\+json|json-?ld|schema\.org/i.test(b.proposed) || /json-?ld|schema/i.test(b.label)
  );
  const ogBlock = find(/property=["']og:|open\s*graph|og:title|og:description/i);

  const jsonldTypes = jsonldBlock
    ? [...jsonldBlock.proposed.matchAll(/"@type"\s*:\s*"([^"]+)"/g)].map((m) => m[1])
    : [];

  const row = (
    label: string,
    original: string,
    present: boolean,
    proposed: string,
    state: MetaRow["proposedState"]
  ): MetaRow => ({ label, original, present, proposed, proposedState: state });

  return [
    row(
      "Title tag",
      s.title || "— missing —",
      !!s.title,
      titleBlock ? titleBlock.proposed : s.title || "—",
      titleBlock ? "updated" : "kept"
    ),
    row(
      "Meta description",
      s.meta_description || "— missing —",
      !!s.meta_description,
      descBlock ? (descBlock.proposed || "added") : s.meta_description || "—",
      descBlock ? (s.meta_description ? "updated" : "added") : "kept"
    ),
    row(
      "Canonical URL",
      s.canonical || "— missing —",
      !!s.canonical,
      canonicalBlock ? "set" : s.canonical || "—",
      canonicalBlock ? (s.canonical ? "updated" : "added") : "kept"
    ),
    row(
      "Structured data (JSON-LD)",
      s.has_jsonld ? s.schema_types.join(", ") || "present" : "— none —",
      s.has_jsonld,
      jsonldBlock ? jsonldTypes.join(", ") || "schema added" : s.has_jsonld ? s.schema_types.join(", ") : "—",
      jsonldBlock ? (s.has_jsonld ? "updated" : "added") : "kept"
    ),
    row(
      "Open Graph tags",
      "— not detected —",
      false,
      ogBlock ? "added" : "—",
      ogBlock ? "added" : "kept"
    ),
    row("Author", s.has_author ? "present" : "— missing —", s.has_author, s.has_author ? "present" : "—", "kept"),
    row(
      "Published / modified",
      [s.published_date, s.modified_date].filter(Boolean).join(" / ") || "— missing —",
      !!(s.published_date || s.modified_date),
      [s.published_date, s.modified_date].filter(Boolean).join(" / ") || "—",
      "kept"
    ),
    row(
      "AI crawler access",
      s.blocks_ai_crawlers ? "blocked ✕" : "allowed",
      !s.blocks_ai_crawlers,
      s.llms_txt_present ? "llms.txt present" : "—",
      "kept"
    ),
  ];
}

const STATE_CHIP: Record<MetaRow["proposedState"], string> = {
  kept: "bg-slate-100 text-slate-400",
  added: "bg-emerald-100 text-emerald-700",
  updated: "bg-yellow-200 text-yellow-900",
};

export default function TechnicalMap({
  signals,
  rewrite,
}: {
  signals: PageSignals | null;
  rewrite: PageRewrite;
}) {
  if (!signals)
    return <p className="text-sm text-slate-400">No page signals available for this run.</p>;

  const origOutline = parseHeadings(signals.headings);
  const propOutline = proposedHeadings(origOutline, rewrite.content_blocks);
  const rows = buildMetaRows(signals, rewrite);

  return (
    <div className="space-y-4">
      {/* Heading outline */}
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="card p-4">
          <div className="section-title mb-2">Original — heading outline</div>
          <Outline items={origOutline} />
        </div>
        <div className="card border-l-2 border-accent p-4">
          <div className="section-title mb-2 text-accent-dark">Proposed — heading outline</div>
          <Outline items={propOutline} />
        </div>
      </div>

      {/* Meta / schema map */}
      <div className="card overflow-hidden">
        <div className="grid grid-cols-[1.1fr_1.1fr_1.1fr] gap-px bg-slate-100 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          <div className="bg-slate-50 px-3 py-2">Metadata / schema</div>
          <div className="bg-slate-50 px-3 py-2">Original</div>
          <div className="bg-slate-50 px-3 py-2 text-accent-dark">Proposed</div>
        </div>
        <div className="divide-y divide-slate-100">
          {rows.map((r) => (
            <div key={r.label} className="grid grid-cols-[1.1fr_1.1fr_1.1fr] gap-px">
              <div className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-navy-900">
                <span className={r.present ? "text-emerald-500" : "text-rose-400"}>
                  {r.present ? "✓" : "✗"}
                </span>
                {r.label}
              </div>
              <div className="break-words px-3 py-2 text-xs text-slate-500">{r.original}</div>
              <div className="px-3 py-2 text-xs">
                <span className={`rounded-sm px-1.5 py-0.5 ${STATE_CHIP[r.proposedState]}`}>
                  {r.proposedState}
                </span>{" "}
                <span className="break-words text-slate-700">{r.proposed}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
