# GEO Optimization Assistant — Project Summary

> A consolidated record of what we designed, built, decided, and verified for the
> **AI assistant for Generative Engine Optimization (GEO)** MVP.
> Last updated: 2026-05-30.

---

## 1. What the system does

An AI assistant that analyzes whether a web page is likely to be **cited by AI search
engines** (ChatGPT, Google AI Overviews, Perplexity, Gemini) for a set of queries, whether it
**communicates the strategic goals** intended, and returns a **consulting-grade report** with
**concrete, prioritized recommendations**.

**Inputs**
- **1 URL** (the page to analyze)
- **Multiple queries** (the questions you want the page to win citations for)
- **A strategic-goals document** (PDF/Word) — optional per run

**Output**
- Executive summary + overall GEO score (0–100)
- Per-engine citation-readiness scores (observed vs. predicted)
- Strategic-goal alignment + query-coverage assessment
- Prioritized recommendations (P0–P3), each with *why it matters*, *expected impact*,
  *effort*, *confidence*, and supporting evidence
- Export to PDF / Markdown, plus saved history

---

## 2. Key decisions (from discovery)

| Area | Decision |
|------|----------|
| Tech stack | Python 3.11 + **FastAPI** backend, **Next.js 15 + TypeScript** frontend |
| Analysis brain (role #1) | **LiteLLM** gateway; Claude default, switchable to GPT/Gemini/Qwen/Kimi. *Currently defaulted to **OpenAI GPT** because the Anthropic account had no credits.* |
| Target engines (role #2) | UI selector — ChatGPT + AI Overviews to start (extensible to Perplexity/Gemini) |
| Analysis modes | **Single-select per run** (4 modes, below) |
| Inputs | 1 URL + multiple queries + 1 strategic-goals doc |
| Knowledge base | ~20 pages of pillar docs, parsed and injected **in-context** (no RAG yet) |
| Output | Consulting-style dashboard + PDF/Markdown export + SQLite history |
| Auth | None (local MVP; add later for a server) |

### The two distinct "model" roles
- **Role #1 — Analysis brain:** the LLM that *runs* the system (reads page + goals + KB,
  writes the diagnosis and recommendations). Chosen via the model picker.
- **Role #2 — Target engines:** the real AI search systems we *optimize for*. They are the
  **subject** of the analysis, selected per run.

### The four analysis modes (pick one per run)
1. **GEO factors + knowledge base** — score the page against known GEO/AEO factors
   (structure, answerability, authority, schema/JSON-LD, freshness, crawlability…) grounded in
   the pillar docs. Primary recommendations engine. *Needs only the analysis-brain key.*
2. **Simulation** — the brain **role-plays each target engine**, answers the queries as that
   engine would, and judges whether it would cite the URL (prediction, no external call).
3. **Live query** — actually queries real engines and checks if the URL is cited
   (**Perplexity API** + **SerpApi** for AI Overviews). *Observed* evidence.
4. **Peec AI data** — pulls real tracked visibility/citation metrics from **Peec AI**.

All modes feed a **shared synthesis + prioritization** step that produces one unified report.

---

## 3. Architecture overview

```
Frontend (Next.js)  ──REST + SSE──▶  Backend (FastAPI, async)
                                       ├─ Ingestion: URL fetch + doc parse + KB loader
                                       ├─ Mode (1 of 4): peec / simulation / live / geo_factors
                                       ├─ Synthesis (LiteLLM brain) → structured analysis
                                       ├─ Prioritization (impact×confidence÷effort → P0–P3)
                                       ├─ Storage: SQLite (runs + content cache)
                                       └─ Export: Markdown + Playwright PDF
```

### Backend layout (`backend/app/`)
- `main.py`, `config.py` — app entry + settings (.env)
- `core/` — `llm.py` (LiteLLM wrapper, structured output, prompt caching), `models.py` (model registry)
- `ingestion/` — `url_fetcher.py`, `doc_parser.py`, `kb_loader.py`
- `modes/` — `geo_factors.py`, `simulation.py`, `live_query.py`, `peec.py` (+ `base.py`)
- `analysis/` — `signals.py`, `synthesis.py`, `prioritization.py`, `schemas.py`, `orchestrator.py`
- `integrations/` — `perplexity.py`, `serp.py`, `peec.py`
- `storage/` — `db.py`, `models.py`, `repository.py`
- `export/` — `markdown.py`, `pdf.py`
- `api/` — `meta.py` (health/models/options), `analyze.py` (SSE), `runs.py` (history + export)
- `tests/` — prioritization, signals, doc parser (9 tests)

### Frontend layout (`frontend/`)
- `app/page.tsx` — New Analysis form (URL, queries, goals upload, mode/engine/model pickers, SSE progress)
- `app/results/[id]/page.tsx` — report dashboard
- `app/history/page.tsx` — past runs
- `components/` — `Report.tsx`, `ScoreGauge.tsx`, `PriorityMatrix.tsx`
- `lib/api.ts` — typed API client + SSE reader
- Styling: Tailwind, consulting palette (navy/slate/teal), no trademarked assets

---

## 4. How the model is prompted

The prompt is **assembled per run**, not a single fixed string:

1. **System prompt** (`analysis/synthesis.py::_SYSTEM`) — instructs the brain to act as a senior
   GEO strategist: assess citation likelihood per engine, assess goal/query alignment, and
   produce focused, evidence-backed recommendations with impact/effort/confidence.
2. **Cache-prefix** — the **knowledge base** text is prepended to the system message (cached on
   Claude via `cache_control`; sent inline on other providers).
3. **JSON-schema instruction** (`core/llm.py`) — auto-appended; forces a single JSON object
   matching the `LLMAnalysis` schema, with a one-shot repair retry on validation failure.
4. **User message** (`synthesis.py`) — the per-run data: mode framing, target engines, queries,
   strategic-goals text, and the mode's **evidence block** (e.g. the extracted page-signal
   briefing for GEO mode, or simulated/observed citations for other modes).

---

## 5. How documents are accessed (techniques)

Two document types, both using **direct text extraction + in-context injection** (no
embeddings/RAG yet — intentional, given the small volume):

- **Strategic-goals doc (per run):** uploaded as `multipart/form-data` → `UploadFile` →
  `doc_parser.parse_document()` → text placed in the user prompt (`## Strategic goals`).
- **Knowledge base (pillars):** files in `Knowledge_base/` read from disk by
  `kb_loader.load_kb_context()`, parsed, concatenated, memoized (`@lru_cache`), injected as the
  cache-prefix.

**Parsing per format** (`ingestion/doc_parser.py`):
- **PDF → PyMuPDF (`fitz`)** — text extracted page by page.
- **Word `.docx` → python-docx** — paragraphs read; heading styles mark section boundaries.
- **`.txt` / `.md`** — decoded and split on blank lines.

**Notes & limits**
- PDFs must contain real text; **scanned/image PDFs need OCR** (not yet included).
- KB is cached at process start — **restart the backend after adding pillar docs**.
- **Upgrade path:** `load_kb_context()` can be swapped for a chunk→embed→vector-store→top-k
  retriever with no caller changes if the KB grows large.

---

## 6. URL fetching & GEO signals (`ingestion/url_fetcher.py`)

- Raw HTTP fetch (httpx) **plus** an optional **Playwright** render — diffed to detect
  **JS-dependent content** that non-rendering AI crawlers would miss.
- Main content via **trafilatura**; structure via **selectolax**.
- Signals extracted: title, meta description, canonical, lang, headings outline, word count,
  **JSON-LD / schema.org types**, author, published/modified dates, **robots.txt / llms.txt**
  presence, whether the site **blocks known AI crawlers** (GPTBot, PerplexityBot, etc.).
- Fetched signals are cached (hash-keyed) to avoid refetching.

---

## 7. Prioritization logic (`analysis/prioritization.py`)

Deterministic (not left to the model):
`score = impact × confidence ÷ effort_weight` (low=1, medium=2, high=3), then bucketed:
**P0 ≥ 8, P1 ≥ 4, P2 ≥ 2, else P3**, sorted most-impactful first. This is what drives the
ranked action cards and the impact/effort matrix.

---

## 8. How to run

**Backend (Terminal 1):**
```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --port 8741 --reload
```
- API only — `GET /` returns 404 by design. Health check: `http://127.0.0.1:8741/api/health`.
  Docs: `http://127.0.0.1:8741/docs`.
- The `LiteLLM ... botocore` warnings are harmless (unused AWS providers).

**Frontend (Terminal 2):**
```bash
cd frontend
npm run dev          # http://localhost:3000
```

**Use it:** open http://localhost:3000 → enter URL + queries + (optional) goals doc → pick a
mode (GEO factors works with just the OpenAI key) → Run → view dashboard → export PDF/MD.

**Tests:** `cd backend && .venv/bin/python -m pytest -q`

---

## 9. Current status (verified)

- ✅ Backend imports, boots, all endpoints respond; SQLite initializes.
- ✅ 9/9 unit tests pass (prioritization, signals, doc parser).
- ✅ Frontend builds clean (no TS errors), all routes compile.
- ✅ Real URL fetch + signal extraction verified (example.com, anthropic.com).
- ✅ Markdown + 2-page Playwright PDF export verified on a real result.
- ✅ **Full real analysis ran end-to-end with GPT** against
  `anthropic.com/news/claude-3-5-sonnet`: overall score **78/100**, ChatGPT 80 / AI Overviews
  75, two **P0** recommendations (add canonical tag, add JSON-LD) grounded in real page signals.
- ✅ SSE pipeline + graceful error handling verified (no-credits error surfaced cleanly and
  saved as an error run).

---

## 10. Configuration & secrets

All keys live in **gitignored** `backend/.env` (copy from `.env.example`):
- `ANTHROPIC_API_KEY` — Claude brain (account currently out of credits)
- `OPENAI_API_KEY` — GPT brain (**current default**, `DEFAULT_MODEL=gpt`)
- `GEMINI_API_KEY`, `OPENROUTER_API_KEY` (Qwen/Kimi) — optional brains
- `PERPLEXITY_API_KEY`, `SERPAPI_API_KEY` — Live mode
- `PEEC_API_KEY` — Peec mode

> ⚠️ **Security:** real Anthropic and OpenAI keys were pasted during development and are in the
> chat transcript — **rotate both** in their respective consoles. `.gitignore` covers `.env`,
> `.venv`, and `*.db`.

---

## 11. Suggested next steps

- Add the **~20 pillar docs** to `Knowledge_base/` to ground recommendations in your GEO playbook.
- Add **Perplexity + SerpApi** keys to enable **Live mode** (real AI-Overviews citation checks).
- Optional enhancements discussed: **OCR fallback** for scanned PDFs, **RAG upgrade** for a
  larger KB, a **"KB status" endpoint** to show loaded pillar docs in the UI, richer per-factor
  scorecards, and prompt tuning (tone/aggressiveness of recommendations).
- Re-enable Claude later: add Anthropic credits and set `DEFAULT_MODEL=claude-default`.
