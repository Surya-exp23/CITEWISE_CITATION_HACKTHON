# CiteWise demo dataset

Built 2026-10-13 for the CiteWise hackathon demo. **Real OpenAlex records +
deliberately planted synthetic noise** so the cleaning pipeline has something
visible to clean.

## Institution & researchers (all real)

| Key | Researcher | ORCID | Field |
|-----|-----------|-------|-------|
| A1 | Nikhil Tandon | 0000-0003-4604-1986 | Endocrinology |
| A2 | Sameer Bakhshi | 0000-0001-9367-4407 | Oncology |
| A3 | Manjari Tripathi | 0000-0003-2201-5644 | Neurology |
| A4 | Rakesh Lodha | 0000-0003-2608-1163 | Pediatrics |
| A5 | Peush Sahni | 0000-0002-6910-062X | Surgery |

Institution: **All India Institute of Medical Sciences, New Delhi** —
ROR `https://ror.org/02dwcqs71`, OpenAlex `https://openalex.org/I63739035`.

## What is real vs synthetic

- **Real** (`is_synthetic=false`): 696 works, 10,421 authors, 2,877 institutions,
  749 citation rows — fetched live from the OpenAlex API on 2026-10-13
  (25 works per researcher sorted by `cited_by_count`, plus citing works).
  Every raw API response is cached in `../cache/<sha1-of-url>.json`, so the demo
  runs fully offline.
- **Synthetic** (`is_synthetic=true`, planted by `scripts/make_messy_data.py`
  with `random.seed(42)` — deterministic): **200 works and 1,146 citation rows**.

> **UI disclosure banner text (copy-paste):**
> "Demo data: real OpenAlex records plus 1,146 deliberately planted synthetic
> rows (duplicate records, repeated in-text mentions, look-alike titles) to
> demonstrate the cleaning pipeline."

## Planted noise inventory (all synthetic, all disclosed)

| # | Noise | Count | Purpose |
|---|-------|-------|---------|
| 1 | Duplicate work records (`DUP1…`) — stripped DOI, title typo, colon→dash, US/UK spelling flip, dropped subtitle word, medRxiv preprint version | 151 alias records | Dedup cascade L1–L3; ~30% also duplicate 1–2 citation rows → `duplicates_removed` in the waterfall |
| 2 | Repeated mention rows (invented context sentences, sections) | 1,024 rows on ~30% of citation pairs (up to 7 mentions per pair) | Mention collapse: 7 mentions → exactly 1 citation |
| 3 | Look-alike traps (`TRAP1…TRAP6`): 3 pairs differing only by "Part 1/Part 2" or "Trial 1/Trial 2", overlapping authors | 3 pairs | The "different part" guard — these must NEVER auto-merge; listed in `ground_truth.traps_not_merged` |
| 4 | Retracted work (`RET1`) + 1 synthetic citation to it | 1 work, 1 row | `cites_retracted` integrity flag (no retracted work existed in the fetched slice, so this one is synthesized) |
| 5 | Citation ring: 4 synthetic authors × 4 works, every ordered pair exchanges exactly 4 citations | 16 works, 48 rows | `citation_ring` integrity flag; authors in `ground_truth.ring_authors` |
| 6 | Preprint→published pair (`PRE1` medRxiv 2023 → `PUB1` journal 2024, identical title, same authors) | 2 works | `preprint_to_published` merge (no real preprint pair was in the fetched slice) |

## Coverage (verified by the build script)

Researcher-scope classification over canonical edges:

| Researcher | Unique citations | self | internal | external |
|------------|-----------------|------|----------|----------|
| A1 (Tandon) | 116 | 10 | 5 | 101 |
| A2 (Bakhshi) | 50 | 1 | 0 | 49 |
| A3 (Tripathi) | 55 | 0 | 1 | 54 |
| A4 (Lodha) | 74 | 2 | 0 | 72 |
| A5 (Sahni) | 50 | 0 | 0 | 50 |

Global: 13 self / 6 internal / 326 external — all three classes present, no
synthetic patching was needed. Waterfall invariants
(`raw − duplicates_removed − repeated_mentions == unique == self+internal+external`)
were asserted for every researcher during the build.

Tip for the demo: **A1 (Nikhil Tandon)** is the richest researcher page, and two
of the internal citations match only on a *middle* author — perfect for the
policy-page demo of switching `citing_authors_considered` any → first_last.

## Files

| File | Contents |
|------|----------|
| `works.json` | 896 records: `record_id, openalex_id, doi, pmid, pmcid, title, year, venue, pub_type, is_preprint, is_retracted, source, is_synthetic` |
| `authors.json` | 10,433 authors: `author_key, openalex_id, orcid, display_name` (A1–A5 are the researchers) |
| `institutions.json` | 2,877 institutions: `ror_id, openalex_id, name, country_code` |
| `authorships.json` | 24,934 rows: `work_record_id, author_key, institution_ror, position, raw_affiliation` |
| `raw_citation_rows.json` | 1,895 rows: `raw_citing_record_id, raw_cited_record_id, row_kind (reference_entry\|mention), context_sentence, section, source, is_synthetic` |
| `ground_truth.json` | `expected_merges` (175 pairs with reasons), `unique_citations_per_researcher`, 57 `sample_classifications` (self/internal/external), `traps_not_merged`, `ring_authors`, `stats` |
| `clean/` | The pre-noise dataset (same schema, all real) — input to `make_messy_data.py` |

## Regenerating

```bash
cd ~/workspace/citewise/backend
python3 scripts/fetch_demo_data.py   # real data from OpenAlex (cached; offline-safe rerun)
python3 scripts/make_messy_data.py   # deterministic noise (seed=42) -> data/demo/
```

Dependencies: `requests`, `tenacity` (`pip install requests tenacity`).
Full JSON load takes ~0.25s — comfortably inside the 30s seed budget.

## Honest limitations (say these in the pitch)

- Citing-work coverage is a sample (≤25 per blockbuster paper, ≤10 per
  researcher paper), not the full citation graph — OpenAlex has the rest.
- Author/institution matching reuses OpenAlex's own disambiguation; name-only
  matches are flagged, not trusted.
- Mention sentences on synthetic rows are invented; real mention extraction
  needs Europe PMC full text (open-access papers only).
- The retracted work, citation ring, traps, and preprint pair are synthetic by
  design — they are the test fixtures, clearly flagged.
