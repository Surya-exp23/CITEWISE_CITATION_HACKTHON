# CiteWise — Teammate Setup Guide (Windows)

You build the UI tomorrow. This guide gets the backend running on your Windows
machine and shows you which endpoint feeds which page.

## 1. Prerequisites

- **Python 3.11+** — https://www.python.org/downloads/ (tick "Add python.exe to PATH")
- **Node 20+** — for the UI (later)
- No Postgres, no Docker, no system libraries needed.

## 2. Backend setup (exact commands)

Open PowerShell in `citewise/backend/`:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python scripts/seed_db.py
uvicorn app.main:app --reload --port 8000
```

`seed_db.py` takes ~25–30s. It prints the top researcher URLs at the end —
keep them, you need them below.

## 3. Confirm it's working

- `GET http://localhost:8000/health` → `{"status":"ok",...}`
- Open http://localhost:8000/docs — interactive Swagger UI, try any endpoint.

## 4. API tour (endpoint → frontend page)

Base URL for the UI: `http://localhost:8000/api`
(Frontend env: `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api`.
CORS already allows `http://localhost:3000`.)

| Page | Endpoint | Example |
|---|---|---|
| Researcher report | `GET /api/researchers/{id}/report` | `/api/researchers/824/report` |
| Researcher papers | `GET /api/researchers/{id}/papers?page=1&page_size=20` | — |
| Institution report | `GET /api/institutions/{id}/report` | `/api/institutions/1/report` (AIIMS demo) |
| Leaderboard | `GET /api/institutions/{id}/researchers` | `/api/institutions/1/researchers` |
| Institutions list | `GET /api/institutions` | — |
| Waterfall | `GET /api/waterfall?scope_type=researcher&scope_id=824` | — |
| Paper citations | `GET /api/papers/{id}/citations?class=external` | — |
| Citation evidence (drawer) | `GET /api/citations/{id}/evidence` | — |
| Integrity flags | `GET /api/integrity?scope_type=researcher&scope_id=824` | — |
| Review queue | `GET /api/review` | — |
| Review decision | `POST /api/review/{id}/decision` `{"decision":"approve"}` | — |
| Review co-pilot | `GET /api/review/{id}/suggestion` | LLM suggestion (flag-gated) |
| Policies | `GET /api/policies`, `PUT /api/policies/{id}` | recompute + version bump |
| Generate report | `POST /api/reports` `{"scope_type":"researcher","scope_id":824,"policy_id":1}` | returns `report_id` + `root_hash` |
| Report PDF | `GET /api/reports/{id}/pdf` | — |
| Public verify | `GET /api/verify/{report_id}` | → `MATCH`/`MISMATCH` |

Use the researcher ids printed by `seed_db.py` (top 8). Institution `1` is the
All India Institute of Medical Sciences demo org.

## 5. Test suite

```powershell
pytest -q
```
19 tests (PRD T1–T15), all must pass. The demo-integration tests take ~40s.

## 6. Demo data

`data/demo/` is **real OpenAlex data** (696 works, 749 citation rows from AIIMS
New Delhi researchers) **plus deliberately planted synthetic noise** (200 works,
1,146 rows: duplicate records, repeated mentions, Part-1/Part-2 traps, a
citation ring, a retracted paper — all flagged `is_synthetic=true`) to make the
cleaning pipeline visible. Full breakdown in `data/demo/README.md` — including
the copy-paste UI disclosure banner text. `ground_truth.json` holds the expected
merges/counts the tests assert against. To regenerate after data edits, see
`scripts/` (run the pipeline, dump the new expectations).

To ingest your own CSV instead:
`POST /api/ingest/csv` with columns
`citing_title,citing_doi,citing_year,citing_authors,citing_affiliations,cited_title,cited_doi,cited_year,cited_authors,context_sentence`.

## 7. AI features (the "Best Use of AI" story)

1. **Intent badges** — every citation classified self/internal/external with an
   AI intent label (`citations.intent`). Show as badges on the paper page.
2. **Semantic dedup** — L3b semantic level merges title variants; surfaced in
   `merge_reason` / review queue.
3. **LLM review co-pilot** — `GET /api/review/{id}/suggestion` returns an
   approve/reject suggestion with rationale. Gated by `ENABLE_LLM_ASSIST`
   (off by default; needs `GROQ_API_KEY` — free at console.groq.com/keys).
4. **NL explanations** — integrity flags carry a plain-English `details.note`;
   evidence records include `explanation` text.

Demo tip: open a researcher report, click a citation to open the evidence
drawer, then flip the policy (`PUT /api/policies/1` with
`{"config": {"citing_authors_considered": "first_last"}}`) and watch the
verified counts change — then show the report PDF with its QR code verifying
at `/api/verify/{id}`.

## 8. Troubleshooting

- `torch` / `sentence-transformers` are **optional** — skip them; semantic
  dedup falls back to fuzzy matching.
- `GROQ_API_KEY` is **optional** — LLM assist stays off unless you enable it.
  Free key, no credit card: https://console.groq.com/keys — then set
  `ENABLE_LLM_ASSIST=true` in `.env`.
- Port 8000 busy? `uvicorn app.main:app --port 8001`.
- `seed_db.py` slow first run is normal (~30s); re-runs are idempotent.
- If `pip install` fails on Windows, upgrade pip first: `python -m pip install --upgrade pip`.

## 9. Hackathon-morning checklist

- [ ] `uvicorn` running, `/health` returns ok
- [ ] `seed_db.py` completed, researcher ids noted
- [ ] `/docs` loads, one report endpoint returns 200
- [ ] Frontend `.env.local`: `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api`
- [ ] `pytest -q` green (run once in the morning)
- [ ] Bookmark: report PDF URL + verify URL for the jury demo
