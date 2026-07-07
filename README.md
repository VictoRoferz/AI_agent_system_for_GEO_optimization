# AI Agent System for GEO Optimization

An AI assistant for **Generative Engine Optimization (GEO)** — analyzes a web page's
readiness to be **cited by AI search engines** (ChatGPT, Google AI Overviews, Perplexity,
Gemini) for a set of queries, checks alignment with your **strategic goals**, and returns a
consulting-grade report with **prioritized, actionable recommendations**.

## What it does

Inputs: **one URL** + **multiple queries** + a **strategic-goals document** (PDF/Word).
Output: an executive summary, per-engine citation-readiness scores, a goal/query alignment
assessment, and prioritized recommendations (each with *why it matters*, *expected impact*,
*priority* P0–P3) — viewable in a dashboard and exportable to PDF/Markdown.

### Two model roles (kept separate)
- **Analysis brain** (the LLM that runs the system): Claude by default, switchable to
  GPT / Gemini / Qwen / Kimi via the model picker (LiteLLM).
- **Target engines** (what we optimize *for*): ChatGPT, AI Overviews, Perplexity, Gemini.

### Four analysis modes (pick one per run)
1. **GEO factors + knowledge base** — score the page against known GEO/AEO factors, grounded
   in your pillar docs. (Recommendations engine; needs only the analysis-brain key.)
2. **Simulation** — the brain role-plays each engine answering your queries and judges whether
   it would cite the page (prediction).
3. **Live query** — actually query real engines and check if the URL is cited (Perplexity API +
   SerpApi for AI Overviews). *Observed* evidence.
4. **Peec AI data** — pull real tracked visibility/citation metrics from Peec AI.

## The optimization agent

After (or straight from) an analysis, a **multi-phase autonomous agent** does the whole
optimization work — watch it live in an activity timeline, with every change explained:

- **Plan** — a Senior GEO Strategist decides per-block actions and a style brief.
- **Audit** — an **expert panel** (Technical GEO Engineer, Content & Answerability Strategist,
  Evidence & Compliance Officer, Brand & Entity Visibility Expert) checks the page against a
  **canonical factor list** extracted once from your KB (cached per KB content hash).
- **Rewrite** — every content block (batched), plus technical changes (JSON-LD, meta,
  canonical) and net-new sections at full depth; every change carries a structured
  **rationale** (KB factors, verbatim page evidence, targeted queries, expected effect).
- **Verify** — deterministic checks (no invented numbers, compliance lexicon, coverage) plus
  LLM lenses (Domain Fidelity Guardian, Compliance Officer), one revision loop, and an LLM
  Retrieval Expert judging **before → after citation-readiness** per engine (predicted).
- **Export** — a deployable optimized HTML page (`/export-page`) and a markdown
  **change package** (`/change-package`) with every change + why + verification status.

Depths: **quick** (~8-12 LLM calls, 1 option per block — for cheap testing, the default) and
**full** (~18-22 calls, 3 options per block + verification loop). Trigger from the studio
("Start optimization"), the report CTA, or the form's "Continue into optimization" toggle;
`POST /api/runs/{id}/optimize?depth=quick|full` via curl. Runs are resumable after a page
reload (the step trace is persisted mid-run) and idempotent (re-POST replays instantly).

> Cost note: the agent fans out many calls sharing one KB+factor prefix — on Claude this
> prefix is cached (`cache_control`), making runs markedly cheaper than on GPT.

## Project layout

```
backend/    FastAPI + LiteLLM + ingestion + modes + synthesis + storage + export
frontend/   Next.js consulting-style dashboard
Knowledge_base/   drop your ~20 pages of GEO pillar docs (PDF/Word) here
```

## Setup

### 1. Backend
```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m playwright install chromium     # for JS rendering + PDF export
cp .env.example .env                                # then fill in ANTHROPIC_API_KEY (at minimum)
.venv/bin/python -m uvicorn app.main:app --port 8741 --reload
```

Required for an analysis run: `ANTHROPIC_API_KEY` (or another configured provider).
Optional: `PERPLEXITY_API_KEY` + `SERPAPI_API_KEY` (Live mode), `PEEC_API_KEY` (Peec mode).

### 2. Frontend
```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```
The frontend talks to the backend at `http://localhost:8741` (override with
`NEXT_PUBLIC_API_BASE`).

### 3. Knowledge base
Drop your GEO pillar documents (PDF / Word / .md / .txt) into `Knowledge_base/`. They are
parsed once and injected into the analysis (cached on Claude via prompt caching). The system
runs without them, but recommendations are best when grounded in your pillars.

## Tests
```bash
cd backend && .venv/bin/python -m pytest -q
```

## Notes
- MVP runs locally, no auth. Server-ready (CORS, async, SSE).
- `backend/.env` is gitignored — never commit real keys.

## Share it online (quick public link)

Let people on other networks open the app via a free Cloudflare tunnel — no deploy, no account.

```bash
brew install cloudflared      # one time
./share.sh                    # starts backend + frontend + tunnel
```

`share.sh` starts the backend (`127.0.0.1:8741`) and the frontend (`:3000`, which proxies `/api/*`
to the backend so there's no CORS), then prints a public `https://<name>.trycloudflare.com` URL.
Share that URL; keep the terminal open; press **Ctrl-C** to stop everything.

Notes: the link lives only while `share.sh` runs on your Mac and the random name **changes each
restart**; anyone with the link can use it (it spends LLM tokens) — your API keys stay server-side.
For an always-on permanent URL, host it on Render/Railway instead.
