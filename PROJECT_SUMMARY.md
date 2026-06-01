# GEO Optimization Assistant — Project Summary

> A consolidated record of what we designed, built, decided, and verified for the
> **Syte AI agent for Generative Engine Optimization (GEO)**.
> Last updated: 2026-06-01.

---

## 1. What the system does

An AI assistant that analyzes whether a web page is likely to be **cited by AI search
engines** (ChatGPT, Google AI Overviews, Perplexity, Gemini) for a set of queries, whether it
**communicates the strategic goals** intended, and returns a **consulting-grade report** with
**concrete, prioritized recommendations** — plus an interactive **"Syte AI agent: optimize
article"** studio that shows the live page side-by-side with the proposed rewrite.

**Inputs**
- **1 URL** (the page to analyze)
- **Multiple queries** (the questions you want the page to win citations for)
- **A strategic-goals document** (PDF/Word) — optional per run

**Output**
- Executive summary + overall GEO score (0–100)
- Per-engine citation-readiness scores (observed vs. predicted)
- Strategic-goal alignment + query-coverage assessment
- **Exhaustive** prioritized recommendations (P0–P3), each with *why it matters*, *expected
  impact*, *effort*, *confidence*, evidence, and a concrete `change` (copy rewrite or exact code)
- **Knowledge-base coverage checklist** — every KB factor marked covered / partial / gap
- **Optimize studio**: full original page vs full proposed page, with in-place change preview
- Export to PDF / Markdown, plus saved history

---

## 2. Key decisions

| Area | Decision |
|------|----------|
| Tech stack | Python 3.11 + **FastAPI** backend, **Next.js 15 + TypeScript** frontend |
| Analysis brain (role #1) | **LiteLLM** gateway; Claude default, switchable to GPT/Gemini/Qwen/Kimi. *Recent runs used **OpenAI GPT** (`DEFAULT_MODEL=gpt`).* |
| Target engines (role #2) | UI selector — ChatGPT + AI Overviews to start (extensible to Perplexity/Gemini) |
| Analysis modes | **Single-select per run** (4 modes, below) |
| Knowledge base | Pillar docs parsed and injected **in-context / full-document** (no RAG — see §5) |
| Compliance | **Always-on** pharma / medtech / healthcare guardrails on every run (see §9) |
| Recommendations | **Exhaustive** against every KB factor (no artificial cap) + coverage checklist |
| Optimize studio | Two full-page panes (original + proposed) from a captured page snapshot (see §8) |
| Output | Consulting-style dashboard + PDF/Markdown export + SQLite history |
| Auth | None (local MVP) |

### The two distinct "model" roles
- **Role #1 — Analysis brain:** the LLM that *runs* the system (reads page + goals + KB, writes
  the diagnosis, recommendations and rewrite). Chosen via the model picker.
- **Role #2 — Target engines:** the real AI search systems we *optimize for*; the **subject** of
  the analysis, selected per run.

### The four analysis modes (pick one per run)
1. **GEO factors + knowledge base** — score the page against known GEO/AEO factors grounded in
   the pillar docs. Primary recommendations engine. *Needs only the analysis-brain key.*
2. **Simulation** — the brain **role-plays each target engine** and judges whether it would cite
   the URL (prediction, no external call).
3. **Live query** — actually queries real engines (**Perplexity API** + **SerpApi** for AI
   Overviews). *Observed* evidence.
4. **Peec AI data** — pulls real tracked visibility/citation metrics from **Peec AI**.

All modes feed a **shared synthesis + prioritization** step producing one unified report.

---

## 3. Architecture overview

```
Frontend (Next.js)  ──REST + SSE──▶  Backend (FastAPI, async)
                                       ├─ Ingestion: URL fetch + render + snapshot/tagging + doc parse + KB loader
                                       ├─ Mode (1 of 4): peec / simulation / live / geo_factors
                                       ├─ Synthesis (LiteLLM brain) → analysis + KB-coverage (compliance-aware)
                                       ├─ Prioritization (impact×confidence÷effort → P0–P3)
                                       ├─ Studio: rewrite brain (block-by-block, anchored) + chat
                                       ├─ Storage: SQLite (runs + content cache + studio state)
                                       └─ Export: Markdown + Playwright PDF
```

### Backend layout (`backend/app/`)
- `main.py`, `config.py` — app entry + settings (.env)
- `core/` — `llm.py` (LiteLLM wrapper, structured output, prompt caching), `models.py` (registry)
- `ingestion/` — `url_fetcher.py`, **`snapshot.py`** (sanitize + tag content blocks), `doc_parser.py`, `kb_loader.py`
- `modes/` — `geo_factors.py`, `simulation.py`, `live_query.py`, `peec.py` (+ `base.py`)
- `analysis/` — `signals.py`, `synthesis.py`, **`rewrite.py`** (studio brain), `prioritization.py`, `schemas.py`, `orchestrator.py`
- `integrations/` — `perplexity.py`, `serp.py`, `peec.py`
- `storage/` — `db.py`, `models.py` (Run, ContentCache, StudioState), `repository.py`
- `export/` — `markdown.py`, `pdf.py`
- `api/` — `meta.py`, `analyze.py` (SSE), `runs.py` (history/export), **`studio.py`** (rewrite/chat/studio/snapshot)
- `tests/` — prioritization, signals, doc parser, studio, **snapshot**, **kb_coverage** (26 tests)

### Frontend layout (`frontend/`)
- `app/page.tsx` — New Analysis form (URL, queries, goals upload, mode/engine/model pickers, SSE)
- `app/results/[id]/page.tsx` — report dashboard
- `app/results/[id]/studio/page.tsx` — **optimize studio** (panes + technical map + chat)
- `app/history/page.tsx` — past runs
- `components/` — `Report.tsx`, `ScoreGauge.tsx`, `PriorityMatrix.tsx`, **`KBCoverage.tsx`**,
  **`SnapshotFrame.tsx`** (one full-page iframe), **`DiffPanes.tsx`** (two synced frames),
  **`TechnicalMap.tsx`** (outline + meta map), `CopyButton.tsx`
- `lib/api.ts` — typed API client + SSE reader
- Styling: Tailwind, consulting palette (navy/slate/teal); diff highlight palette yellow/green

---

## 4. How the model is prompted

The prompt is **assembled per run**:

1. **System prompt** (`analysis/synthesis.py::_SYSTEM`) — senior GEO strategist; assess citation
   likelihood per engine + goal/query alignment; **be exhaustive** against every KB factor;
   **always apply regulated-industry compliance**; emit a KB-coverage checklist; every
   recommendation must carry a concrete `change`.
2. **Cache-prefix** — the **entire knowledge base** is prepended (cached on Claude via
   `cache_control`; inline on other providers).
3. **JSON-schema instruction** (`core/llm.py`) — auto-appended; forces a single JSON object
   matching the schema, with a one-shot repair retry.
4. **User message** — per-run data: mode framing, target engines, queries, strategic-goals text,
   and the mode's **evidence block**.

The **studio rewrite brain** (`analysis/rewrite.py`) and **chat** use the same KB cache-prefix
and the same always-on compliance guardrails.

---

## 5. How documents are accessed — full-context injection (NOT RAG)

There is **no vector store / embeddings / top-k retrieval**. Both document types use direct text
extraction + in-context injection:

- **Strategic-goals doc (per run):** uploaded `multipart/form-data` → `doc_parser.parse_document()`
  → text in the user prompt (truncated to ~8k chars).
- **Knowledge base (pillars):** `kb_loader.load_kb_context()` reads **every** file in
  `Knowledge_base/`, concatenates them whole, memoizes (`@lru_cache`), and injects as the
  cache-prefix on **every** call. The brain therefore sees **100% of the KB every time** — this
  is what makes recommendations exhaustive against all KB factors.

**Parsing** (`ingestion/doc_parser.py`): PDF → PyMuPDF; `.docx` → python-docx; `.txt`/`.md` → decode.

**Limits & upgrade path**
- KB is cached at process start — **restart the backend after adding pillar docs**.
- Scanned/image PDFs need OCR (not included).
- Full-context injection is great for completeness but bounded by the model context window; for a
  large KB, swap `load_kb_context()` for a chunk→embed→vector-store→top-k retriever (callers
  unchanged). This is the only change needed to make it a true RAG app.

---

## 6. URL fetching, signals & page content (`ingestion/url_fetcher.py`)

- Raw HTTP fetch (httpx) **plus** a **Playwright** render — diffed to detect **JS-dependent
  content**. The render **auto-scrolls** (to trigger lazy assets) and **removes cookie/consent
  overlays** before capture.
- Main content via **trafilatura**; structure via **selectolax**.
- Signals: title, meta description, canonical, lang, headings outline, word count, **JSON-LD /
  schema types**, author, published/modified, **robots.txt / llms.txt**, whether the site
  **blocks known AI crawlers**, JS-dependency.
- Three artifacts are produced with different limits:
  | Artifact | Purpose | Limit |
  |---|---|---|
  | `snapshot_html` | the studio's visual panes | **4 MB** (whole page + images) |
  | `main_text` | text the **analysis brain** reads | **20,000 chars** |
  | `text_blocks` | **anchors** (`data-geo-id`) for the rewrite | **200 blocks**, 400 chars each |
- The rewrite brain additionally reads `main_text[:12000]`.
- Signals (incl. snapshot + text_blocks) are **cached** hash-keyed; cache entries from before
  snapshot capture are **automatically re-fetched** (cache-bust when `snapshot_html` is empty).

---

## 7. Prioritization logic (`analysis/prioritization.py`)

Deterministic: `score = impact × confidence ÷ effort_weight` (low=1, medium=2, high=3), bucketed
**P0 ≥ 8, P1 ≥ 4, P2 ≥ 2, else P3**, sorted most-impactful first. `rank_order()` exposes the
finding→`rec-N` mapping so the KB-coverage checklist can link factors to the rec that fixes them.

---

## 8. The optimize studio (`/results/[id]/studio`)

Opened via the **"✨ Syte AI agent: optimize article"** button on the report.

**Page snapshot & block tagging** (`ingestion/snapshot.py`)
- `sanitize_snapshot()` makes the rendered HTML safe & embeddable: strips `<script>`/`<noscript>`/
  auto-refresh/inline handlers/`javascript:` URLs, injects `<base href>`, **promotes lazy images**
  (`data-src`→`src`, forces eager) so photos render, caps to 4 MB.
- `tag_blocks()` (lxml) assigns a stable **`data-geo-id`** to each outermost content block,
  preferring `<main>` and **skipping nav/header/footer/aside**, and returns the `text_blocks` list
  (id, tag, text) used for anchoring.
- Served via `GET /api/runs/{id}/snapshot`; **excluded** from the main analyze/run payloads to keep
  them lean.

**Anchored rewrite** (`analysis/rewrite.py`)
- The rewrite brain receives the tagged blocks and returns `content_blocks` + `technical_blocks`;
  each content block carries an **`anchor_id`** (the `data-geo-id` it maps to) → near-100% precise
  highlighting, with text matching as fallback. Net-new content has no anchor (correct).

**Two full-page panes** (`components/DiffPanes.tsx`, `SnapshotFrame.tsx`)
- **Left** = the full original site (images, links, layout). Changed text is highlighted **yellow**
  with a **▸ arrow**; clicking it reveals the proposed text in **green** inline (original struck).
- **Right** = the full proposed site with changes applied in **green**.
- Both render in **sandboxed iframes** (`allow-scripts`, opaque origin; our controllers only).
  Cookie overlays are also stripped at render time as a safety net.
- **Scroll-synced** via `postMessage` (parent relays between frames), with a "Sync scroll" toggle.

**Technical structure & metadata** (`components/TechnicalMap.tsx`)
- A **heading outline** (H1→H2→H3 tree) and a **meta/schema map** (title, description, canonical,
  JSON-LD types, Open Graph, author, dates, AI-crawler access) shown **original vs proposed** with
  added/updated chips — plus the exact code blocks (JSON-LD, meta, llms.txt) below.

**Chat** — ask the GEO agent questions or request edits; it applies live block edits and can add
recommendations, all compliance-aware. Studio state (rewrite, chat, suggestions) persists per run.

---

## 9. Compliance & exhaustiveness (always-on)

- **Regulated-industry compliance** is baked into the synthesis, rewrite and chat system prompts:
  treat content as pharma/medtech/biotech/healthcare; **no unsubstantiated promotional language**;
  every efficacy/safety/superiority/outcome claim must be backed by a citable study/clinical
  data/regulatory approval (or softened / flagged); avoid absolute & comparative claims and
  off-label implications; **flag existing non-compliant claims as P0**; all proposed copy must
  itself be compliant.
- **Exhaustive recommendations**: the old "~3 recommendations" cap was removed; the brain evaluates
  the page against **every** KB factor.
- **KB-coverage checklist** (`schemas.KBCoverageItem` → `Report`/`KBCoverage.tsx`): one row per KB
  factor with **covered / partial / gap** and links to the recommendation(s) that close each gap.

---

## 10. How to run

**Backend (Terminal 1):**
```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --port 8741 --reload
```
- API only — `GET /` returns 404 by design. Docs: `http://127.0.0.1:8741/docs`.
- The `LiteLLM ... botocore` warnings are harmless.

**Frontend (Terminal 2):**
```bash
cd frontend
npm run dev          # http://localhost:3000  (backend CORS allows only :3000)
```

**Use it:** open http://localhost:3000 → URL + queries + (optional) goals doc → pick a mode → Run
→ view dashboard + KB coverage → click **"Syte AI agent: optimize article"** for the panes.

> First analysis of a URL is slower (Playwright render + snapshot). Runs created *before* snapshot
> capture existed need a fresh analysis (or backfill) to populate the studio; new runs work
> automatically.

**Tests:** `cd backend && .venv/bin/python -m pytest -q`  ·  type-check: `cd frontend && npx tsc --noEmit`

---

## 11. Current status (verified)

- ✅ Backend imports, boots, all endpoints respond; SQLite initializes.
- ✅ **26/26 backend unit tests pass** (prioritization, signals, doc parser, studio, snapshot
  sanitizer/tagging, KB-coverage rec-id remapping).
- ✅ Frontend builds clean (`next build`) and type-checks (`tsc --noEmit`), all routes compile.
- ✅ Real URL fetch + render + **snapshot capture** verified on a live MED-EL article
  (~957 KB sanitized HTML, 21 images, 0 scripts, 129 tagged content blocks).
- ✅ **Optimize studio verified visually** (headless Chromium screenshots): full site renders in
  both panes (no cookie overlay), intro highlighted **yellow**, **▸ arrow reveals green**, and the
  **two panes scroll in sync** (left=1600 → right≈1590).
- ✅ **Anchored matching verified**: regenerated rewrite anchored **4/4 changed content blocks**
  (g6/g11/g25/g9), up from 2/3 with text-only matching; net-new block correctly un-anchored.
- ✅ Technical map (outline + meta/schema, original vs proposed) and KB-coverage checklist render.
- ✅ Markdown + Playwright PDF export and SSE error handling verified previously.

---

## 12. Configuration & secrets

All keys live in **gitignored** `backend/.env` (copy from `.env.example`):
- `ANTHROPIC_API_KEY` — Claude brain  ·  `OPENAI_API_KEY` — GPT brain (recent default, `DEFAULT_MODEL=gpt`)
- `GEMINI_API_KEY`, `OPENROUTER_API_KEY` (Qwen/Kimi) — optional brains
- `PERPLEXITY_API_KEY`, `SERPAPI_API_KEY` — Live mode  ·  `PEEC_API_KEY` — Peec mode
- `ENABLE_PLAYWRIGHT=true` — needed for rendering + the studio snapshot

> ⚠️ **Security:** real Anthropic/OpenAI keys were pasted during development and are in the chat
> transcript — **rotate both**. `.gitignore` covers `.env`, `.venv`, and `*.db`.

---

## 13. Suggested next steps

- **Broader rewrite coverage** (optional): raise `_MAX_MAIN_TEXT` (20k), the rewrite's `[:12000]`,
  and `_MAX_BLOCKS` (200); or have the rewrite emit a block for *every* `text_block` so both panes
  diff the entire article.
- **Tighten chrome filtering**: a few leftover menu `<li>`s slip past the nav skip on some sites
  (harmless, never anchored).
- **Real RAG** for large pages/KBs (chunk→embed→top-k) per §5.
- Add the **pillar docs** to `Knowledge_base/`; add **Perplexity + SerpApi** keys for Live mode.
- **OCR fallback** for scanned PDFs; a **"KB status" endpoint** to show loaded pillars in the UI.
- Re-enable Claude: add Anthropic credits and set `DEFAULT_MODEL=claude-default`.
