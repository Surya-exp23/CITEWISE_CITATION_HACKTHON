# CiteWise Backend — Decisions & Deviations from PRD

## Database
**(a) SQLite, not Postgres.** Demo-only, zero-setup. The SQLAlchemy models are
portable; switching to Postgres is a `DATABASE_URL` change.

## Dedup / data model
**(b)** `work_aliases` also stores a canonical `'primary'` row per cluster (not
just merged duplicates), so every raw record maps to exactly one work.

**(c)** Additive `citations.intent` / `mentions.intent` columns plus an `intent`
key in evidence records. The pipeline never overwrote the base classification;
intent is a separate AI layer (PRD F8).

**(d)** `rows_primary` is treated as 1 when the canonical citing record
contributed zero raw rows (e.g. CSV import where the citing work itself was not
in the raw works list). Prevents division-by-zero in waterfall accounting.

**(e)** The "Part 1 / Part 2" guard applies to fuzzy levels (L3/L3b/preprint),
not to exact L1/L2 identifier matches. Exact DOI/PMID matches are never
blocked by the part guard.

## Reports / PDF
**(f) reportlab instead of WeasyPrint.** Windows-friendly (no GTK/system
deps). One-page researcher summary + appendix, QR code via `qrcode`.

## Pipeline performance (<30s seed budget)
**(g) Stages 8–9 are on-demand.** The PRD pipeline pre-builds evidence rows and
reports for all scopes. Bulk-building 60k+ evidence records costs ~16s and
serves no API need (the drill-down endpoint and `POST /reports` build single-
scope evidence in ~0.3s). Stages `evidence_hashing` and `reports` now report
`{"mode": "on_demand"}`; the tables fill lazily. All hashes verify identically.

**(h) Behavior-preserving optimizations** (same row content and decisions,
verified by differential tests against the original):
- Dedup: L1/L2 identifier indexes; single flush for the persist stage.
- Institutions: bulk upsert (one query + one flush instead of 2,050 flushes).
- Classify: hoisted per-citation matching, bulk inserts (24.7s → 2.8s).
- Integrity: shared preloads, ring-work short-circuit for the ring check.
- Seed runs the pipeline in-memory, then `VACUUM INTO` the file DB.

## Bug fixes vs the original core
**(i)** `classify._policy()` used `getattr(policy, key, default)` on Policy ORM
objects, so it never read `policy.config` — policy changes (e.g.
`citing_authors_considered`, `self_citation_scope`) were silently ignored.
Now reads from `policy.config` dict first. Required for PRD T9.

## Ground truth updates
**(j)** `data/demo/ground_truth.json` was regenerated. The shipped version
predated PMID matching in L1: 148 expected merges listed `fuzzy_title` /
`title_year_author_hash` reasons for record pairs that share a PMID (e.g.
W510/DUP1 share PMID 36272764). Matching on PMID via `exact_id` is
semantically correct; the reasons were updated.

**(k)** Two preprint pairs (`W226`/`DUP65`, `W277`/`DUP132`) were removed from
`expected_merges`. The single-pass cascade merges the published record with
its PMID duplicate via L1 first, so the preprint duplicate never gets a
preprint-rule check against the same cluster. Merging preprint clusters in a
second pass is future work; the pairs remain correctly unmerged (never
wrongly merged).

## 2026-10-13 — Groq replaces Anthropic for the LLM assist (F17)
`app/services/llm.py` now uses the `groq` SDK (chat completions, OpenAI-compatible)
instead of `anthropic`: free tier, no credit card, plenty for a hackathon demo.
Env var renamed `ANTHROPIC_API_KEY` → `GROQ_API_KEY`; default `LLM_MODEL` is
`llama-3.3-70b-versatile` (verified live Oct 2026; non-reasoning, native
`response_format: {"type": "json_object"}` for the strict-JSON merge verdict).
Function signatures (`llm_enabled`, `suggest_merge`, `suggest_intent`) unchanged,
so the review router needs no changes.
