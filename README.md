# CiteWise — Medical Citation & Research Impact Intelligence

> **"We don't just give a citation number. We give proof."**

Universities and medical colleges use citation counts to evaluate and promote doctors and researchers — but those counts are often inflated and impossible to verify. CiteWise is an AI-assisted, fully auditable platform that cleans citation data with deterministic rules, explains every number in plain English, and seals every report with cryptographic proof.

Built for a hackathon under the **"Best Use of AI"** theme. Working prototype — no deployment required.

---

## Table of Contents

1. [The Problem](#the-problem)
2. [The Solution](#the-solution)
3. [How It Works](#how-it-works)
4. [Key Concepts Explained](#key-concepts-explained)
5. [AI Features](#ai-features)
6. [Tech Stack](#tech-stack)
7. [Libraries Used](#libraries-used)
8. [Database](#database)
9. [Data & References](#data--references)
10. [Project Structure](#project-structure)
11. [Getting Started](#getting-started)
12. [API Overview](#api-overview)
13. [Demo Script (for judges)](#demo-script-for-judges)
14. [Testing](#testing)
15. [Honest Limitations](#honest-limitations)

---

## The Problem

Citation counts decide promotions, grants, and reputations in medical academia — yet the numbers nobody can audit:

- **Duplicate records** — the same paper exists multiple times (typos, missing DOI, preprint + published version), so citations get double-counted.
- **Mention inflation** — one paper mentioning another 7 times is counted as 7 citations by naive systems.
- **Mixed signals** — self-citations and same-institution citations are lumped together with independent external citations.
- **No proof** — reports are plain numbers. A promotion committee cannot check *why* a number is what it is.

## The Solution

CiteWise turns every citation number into an **auditable record**:

1. **Eliminates duplicate** paper and citation records (with a human review queue for uncertain cases — never silent wrong merges).
2. **Collapses repeated mentions** — 7 mentions of one paper inside one citing publication counts as exactly 1 citation.
3. **Classifies every citation** as *self*, *internal* (same institution), or *external*.
4. **Generates verifiable reports** — every number drills down to its evidence; every report carries a SHA-256 Merkle root, a QR code, and a public verify page.

**Core design principle:** *AI does the reading, rules do the counting.* Machine learning handles judgment calls (disambiguation, intent, explanation); deterministic code guards the arithmetic — so AI is everywhere, but never where it could lie about a number.

---

## How It Works

### The pipeline (9 stages)

Raw data enters at the top; verified, explainable results come out at the bottom:

```
CSV upload / demo dataset
        │
        ▼
┌─────────────────────────┐
│ 1. Ingest               │  Load raw works + citation rows exactly as received
├─────────────────────────┤
│ 2. Normalize            │  Clean DOIs, titles, author names (NFKD, unidecode,
│                         │  British→American spelling map)
├─────────────────────────┤
│ 3. Deduplicate          │  Cascade: exact ID → title/year/author hash →
│                         │  fuzzy title → preprint rule. Uncertain pairs go
│                         │  to the human review queue (never auto-merged)
├─────────────────────────┤
│ 4. Resolve institutions │  Map affiliations to ROR IDs; link authorships
├─────────────────────────┤
│ 5. Build edges+mentions │  Group raw rows into unique (citing, cited) pairs;
│                         │  compute duplicates_removed / repeats_removed
├─────────────────────────┤
│ 6. Classify             │  Label each citation self / internal / external
│                         │  with a stored reason (per scope + policy)
├─────────────────────────┤
│ 7. Metrics & integrity  │  h-index, i10, KPIs, timelines; integrity flags
│                         │  (retractions, citation rings, ratios)
├─────────────────────────┤
│ 8. Evidence & hashing   │  JSON evidence record per citation → SHA-256 leaf
│                         │  → Merkle root per report
├─────────────────────────┤
│ 9. Reports (on demand)  │  PDF with QR code + root hash; public verify page
└─────────────────────────┘
        │
        ▼
FastAPI (/api/…)  →  React frontend
```

### The waterfall (the heart of the demo)

For any researcher or institution, the raw-to-verified arithmetic is shown as an interactive waterfall chart, and **both invariants always hold**:

```
raw_rows
  − duplicates_removed        (rows from duplicate citing records)
  − repeated_mentions         (extra in-text mentions)
  = unique_citations          (distinct citation edges)
  − self_citations
  − internal_citations
  = verified_external         (the headline number)
```

Every bar is clickable and drills down to the underlying citations.

### Request flow at runtime

The pipeline runs **once** (on seed or CSV upload) and stores everything in the database. The API then serves precomputed results — pages load in ~1 second. The only live recomputation is the **policy engine**: changing what counts as "internal" reclassifies and updates every number instantly.

---

## Key Concepts Explained

**Citation vs mention.** A *mention* is one occurrence of a reference inside a paper's text. A *citation* (edge) is the unique pair *(citing paper, cited paper)* — mentioned 7 times still counts once.

**Canonical work / alias.** Dedup merges duplicate records into one *canonical work* (the real paper); the duplicates become *alias records* pointing at it. Merge reasons (`exact_id`, `fuzzy_title`, `preprint_to_published`…) and confidence scores are stored and visible.

**Self / internal / external.** *Self* = the researcher cited their own work. *Internal* = a citation from the same institution (matched by ROR ID). *External* = fully independent. The headline metric is **verified external**.

**Hash (SHA-256).** A fingerprint for data: any input → a fixed 64-character code; change one comma and the fingerprint is completely different. One-way only.

**Evidence record.** A JSON snapshot per citation (who cited whom, classification, the rule that decided it, mention count, source links) fingerprinted with SHA-256 — each citation carries its own tamper-proof seal.

**Merkle root.** All citation fingerprints are paired, hashed, and combined up a tree until one root hash remains — a single code sealing the *entire report*.

**Verify page.** Recomputes the root from stored data and compares: **MATCH** = untouched, **MISMATCH** = tampered. The QR code on the PDF links here.

**Policy engine.** "What counts as internal?" is a setting, not hardcoded — e.g. whether only first/last authors or any author counts for institution matching. Changes recompute live with a version bump.

**Review queue.** Uncertain merges (e.g. "Part 1" vs "Part 2" look-alikes) are never auto-merged; a human approves/rejects side-by-side, with an optional AI suggestion.

**Integrity flags.** Neutral, drill-downable signals: citations to retracted papers, citation rings (graph analysis), abnormal internal/self ratios. Worded as "worth reviewing", never accusations.

---

## AI Features

- **Citation intent classification** — every citation labeled *background / uses / supports / extends / contrasts* from its context sentences (deterministic cue-phrase heuristics; optional LLM path).
- **Semantic dedup** — embedding-based title similarity (sentence-transformers) catches duplicates fuzzy matching misses; scores are precomputed and cached so the demo runs offline.
- **LLM review co-pilot** — for each review-queue item, an LLM (Groq, free tier) returns a strict-JSON verdict `{same_paper, confidence, reason}` shown as a suggestion. Flag-gated (`ENABLE_LLM_ASSIST`), never auto-applies.
- **Natural-language explanations** — every classification and waterfall step gets a plain-English sentence generated from the rule that fired.

---

## Tech Stack

### Backend (`backend/`)
| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| API framework | FastAPI + Uvicorn |
| Validation / config | Pydantic v2, pydantic-settings |
| ORM | SQLAlchemy 2.x |
| Database | SQLite (file-based, zero-setup; schema is Postgres-compatible) |
| LLM provider | Groq (free tier, OpenAI-compatible chat completions) |

### Frontend (`frontend/`)
| Layer | Choice |
|---|---|
| Framework | React 19 + Vite (plain JavaScript) |
| Routing | react-router-dom |
| Styling | Tailwind CSS v4 (light theme) |
| Charts | Recharts (waterfall, timelines) |
| QR codes | qrcode.react |

### Database
SQLite (`citewise.db`, created by the seed script). 15 tables per the domain model: `institutions`, `authors`, `works`, `work_aliases`, `authorships`, `raw_citation_rows`, `citations`, `mentions`, `policies`, `citation_classifications`, `evidence`, `reports`, `review_items`, `rejected_merges`, `integrity_flags` — plus additive `intent` columns on citations/mentions. Chosen for the hackathon because it needs no server, no Docker, no setup; the schema keeps exact PRD table/column names and ports cleanly to PostgreSQL.

---

## Libraries Used

**Backend** (`backend/requirements.txt`):
| Library | Used for |
|---|---|
| `fastapi`, `uvicorn[standard]` | REST API + ASGI server |
| `pydantic>=2`, `pydantic-settings` | Request/response validation, env config |
| `sqlalchemy>=2` | ORM, models, queries |
| `python-multipart` | CSV file uploads |
| `httpx`, `tenacity` | HTTP client + retries for data fetching |
| `pandas` | CSV parsing and validation |
| `rapidfuzz` | Fuzzy title matching (dedup cascade) |
| `unidecode` | Unicode normalization for titles/names |
| `lxml` | (Full-text XML parsing path) |
| `pysbd` | Sentence splitting for mention extraction |
| `networkx` | Citation-ring detection (graph analysis) |
| `qrcode[pil]` | QR codes on PDF reports |
| `reportlab` | Verifiable PDF report generation (Windows-friendly) |
| `jinja2` | Templating support |
| `groq` | LLM review co-pilot (free tier) |
| `pytest`, `pytest-asyncio` | Test suite (PRD tests T1–T15) |
| `sentence-transformers`, `torch` | *Optional* — one-time embedding precompute only |

**Frontend** (`frontend/package.json`):
| Library | Used for |
|---|---|
| `react`, `react-dom` | UI framework |
| `react-router-dom` | Page routing (7 pages) |
| `recharts` | Waterfall, timeline, distribution charts |
| `qrcode.react` | QR rendering |
| `tailwindcss` (+ `@tailwindcss/vite`) | Styling, light theme |
| `vite`, `@vitejs/plugin-react` | Build tooling |

---

## Data & References

### Primary dataset — real OpenAlex records
- **Source:** [OpenAlex](https://openalex.org) API (CC0 bibliographic data) — the open catalog of scholarly works the PRD names.
- **Institution:** All India Institute of Medical Sciences, New Delhi — ROR `https://ror.org/02dwcqs71`.
- **Researchers (all real, with real ORCIDs):** Nikhil Tandon (endocrinology), Sameer Bakhshi (oncology), Manjari Tripathi (neurology), Rakesh Lodha (pediatrics), Peush Sahni (surgery).
- **Size:** 696 real works, 749 real citation rows. Every raw API response is cached under `backend/data/cache/` (keyed by URL hash), so the demo runs fully offline.
- Institution identifiers come from [ROR](https://ror.org); retraction info follows the OpenAlex `is_retracted` flag model (cf. Crossref).

### Planted synthetic noise (fully disclosed)
`backend/scripts/make_messy_data.py` (deterministic, `seed=42`) adds **200 synthetic works / 1,146 synthetic rows**, all flagged `is_synthetic=true`: 151 duplicate records (stripped DOIs, title typos, US/UK spelling flips, medRxiv preprint versions), repeated-mention rows (up to 7 per pair), 3 Part 1/Part 2 look-alike traps, a 4-author citation ring, one retracted work, one preprint→published pair. `backend/data/demo/ground_truth.json` holds the expected merges/counts the tests assert against, and the UI shows a disclosure banner whenever synthetic rows are present.

### Live-demo CSV
`jury_demo.csv` — a hand-built 16-row fixture (fictional researcher Dr. Ananya Rao, AIIMS) where every row triggers a visible pipeline behavior: fuzzy merge, 5-mention collapse, Part-trap review item, preprint merge, self/internal/external split. Upload it on the Ingest page to watch the pipeline work live.

### Method references
- Dedup cascade design: PRD §5.2 (blocking, token-set fuzzy matching, part-guard).
- Waterfall arithmetic + invariants: PRD §5.4.
- Evidence hashing / Merkle root: PRD §11.9 (canonical JSON: sorted keys, no whitespace).
- Citation-ring detection: strongly-connected components via `networkx`.

---

## Project Structure

```
citewise/
├── README.md                  ← you are here
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   ├── app/
│   │   ├── main.py            ← FastAPI app, CORS, error shape
│   │   ├── config.py          ← env settings
│   │   ├── db.py              ← engine, sessions
│   │   ├── models.py          ← 15 SQLAlchemy tables (PRD §10)
│   │   ├── schemas.py         ← Pydantic response models
│   │   ├── pipeline.py        ← the 9-stage pipeline orchestrator
│   │   ├── routers/           ← /api/... endpoints (ingest, researchers,
│   │   │                        institutions, citations, waterfall, policies,
│   │   │                        review, integrity, reports, verify)
│   │   └── services/          ← normalize, dedup, semantic, edges, mentions,
│   │                            classify, intent, explain, metrics, integrity,
│   │                            evidence, waterfall, review, policy, llm,
│   │                            report_pdf, report_view, demo_data
│   ├── scripts/
│   │   ├── seed_db.py         ← one-command demo bootstrap (~23s)
│   │   ├── fetch_demo_data.py ← pulls OpenAlex → data/cache
│   │   ├── make_messy_data.py ← plants deterministic noise → data/demo
│   │   └── precompute_embeddings.py ← optional semantic scores cache
│   ├── data/
│   │   ├── cache/             ← raw OpenAlex API responses (offline demo)
│   │   └── demo/              ← works/authors/citations JSON + ground_truth
│   └── tests/                 ← pytest suite (PRD T1–T15)
└── frontend/
    ├── package.json
    ├── vite.config.js         ← dev server on :3000 (matches backend CORS)
    └── src/
        ├── lib/               ← api.js, hash.js (Web-Crypto verifier), explain.js
        ├── components/        ← WaterfallChart, CitationDrawer, KpiCard,
        │                        PaperTable, Review queue UI, Policy forms…
        └── pages/             ← Overview, Ingest, Institution, Researcher,
                                 Review, Policy, Verify
```

---

## Getting Started

**Prerequisites:** Python 3.11+, Node 20+. No Postgres, Docker, or system libraries needed.

**Backend** — in `backend/` (PowerShell):
```powershell
python -m venv citewise-env
citewise-env\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python scripts/seed_db.py     # ~23s; prints researcher URLs
uvicorn app.main:app --reload --port 8000
```
API docs: http://localhost:8000/docs · health: http://localhost:8000/health

**Frontend** — in `frontend/` (second terminal):
```powershell
npm install
npm run dev
```
App: http://localhost:3000 (CORS is pre-configured). Set `VITE_API_BASE_URL` in `.env` if the API lives elsewhere.

**Enable the LLM co-pilot** (optional): free key at `console.groq.com/keys`, then in backend `.env`: `ENABLE_LLM_ASSIST=true`, `GROQ_API_KEY=…`.

---

## API Overview

Base: `http://localhost:8000/api`. Full interactive docs at `/docs`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/ingest/demo` | Load cached demo data, run pipeline |
| POST | `/ingest/csv` | Upload CSV (10 columns), validate, run pipeline |
| GET | `/institutions`, `/institutions/{id}/report`, `/institutions/{id}/researchers` | Institution data + leaderboard |
| GET | `/researchers/{id}/report`, `/researchers/{id}/papers` | Researcher report (KPIs, waterfall, timeline) |
| GET | `/papers/{id}/citations`, `/citations/{id}/evidence` | Drill-down + evidence drawer |
| GET | `/waterfall` | Raw→verified arithmetic for any scope |
| GET/POST/PUT | `/policies`, `/policies/{id}` | Policy config; PUT recomputes live |
| GET/POST | `/review`, `/review/{id}/decision`, `/review/{id}/suggestion` | Human review queue + AI suggestion |
| GET | `/integrity` | Integrity flags with evidence |
| POST/GET | `/reports`, `/reports/{id}`, `/reports/{id}/pdf` | Verifiable reports + PDF with QR |
| GET | `/verify/{report_id}` | Public: recompute root → MATCH/MISMATCH |

Standard error shape: `{ "error": { "code", "message" } }`. List endpoints paginate via `page`/`page_size`.

---

## Demo Script (for judges) — ~5 minutes

1. **(30s)** The pitch: *"Citation counts are numbers nobody can verify. CiteWise turns them into auditable records — AI reads each citation, rules do the counting."*
2. **(45s) Live ingest:** upload `jury_demo.csv` on the Ingest page — watch the stepper report merges and the review item.
3. **(60s) Researcher page:** the waterfall 16 → 11 → 4 verified external.
4. **(45s)** Click "Repeated mentions collapsed" — 5 sentences, counted once.
5. **(45s) Review queue:** the Part 1/Part 2 pair the system refused to merge.
6. **(45s) Policy page:** flip the internal rule, watch numbers change live.
7. **(45s)** Generate the PDF, scan the QR → verify page: **MATCH**.
8. **(15s)** Close with the honest limitations below.

## Testing

```powershell
pytest -q        # 20 tests, ~40s — PRD T1–T15: normalization, dedup cascade,
                 # Part-guard, mention collapse, classification, policy flip,
                 # verify MATCH/MISMATCH, waterfall invariants, h-index,
                 # rejected-merge memory, ground-truth integration
```

## Honest Limitations

- Citation coverage is a sample of citing works, not the full graph — OpenAlex has the rest.
- Author/institution matching reuses OpenAlex disambiguation; name-only matches are flagged, not trusted.
- Mention sentences on synthetic rows are invented; real mention extraction needs open-access full text.
- The retracted work, citation ring, traps, and preprint pair in the demo are synthetic by design — clearly flagged.
- The hash proves *CiteWise's* report wasn't altered after generation; it doesn't vouch for upstream databases — which is why every record links to its DOI.
- No blockchain, no accounts, no patient data, no automatic promotion decisions — evidence for humans, not a replacement for judgment.

---

*Built overnight for the hackathon: deterministic pipeline + AI layer (backend), 7-page React app (frontend), real OpenAlex data with disclosed synthetic noise. "AI does the reading, rules do the counting — and every number carries its proof."*
