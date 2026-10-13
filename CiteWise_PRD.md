# CiteWise — Product Requirements Document (PRD)

**Medical Citation & Research Impact Intelligence**
Hackathon build spec. Written so a human team or an LLM coding agent (Antigravity, Claude Code, Cursor, etc.) can build the product accurately.

Companion file: `CiteWise_DOCS.md` (glossary, datasets, APIs, libraries, jury Q&A, pitch). Read both before writing code.

---

## 0. Instructions for the coding agent (read first)

1. Read this PRD fully, then `CiteWise_DOCS.md`. Do not skip the counting rules in Section 5. They are the heart of the product.
2. Build in the phases listed in Section 15. After each phase, run the tests in Section 16 and fix failures before moving on.
3. The counting core is deterministic. Do not use an LLM to decide any count, merge, or classification. LLM use is optional, off by default, and limited to suggestions for the human review queue (Section 11.8).
4. Never hardcode result numbers. Every number shown in the UI must be computed from the database and must be traceable to evidence rows.
5. The demo must work fully offline from cached data (`OFFLINE_MODE=true`). External APIs are used only by the fetch scripts and the optional live-ingest feature.
6. Any synthetic (planted) data must carry `is_synthetic = true` in the database and be disclosed in the UI (Section 14).
7. Keep modules small and typed. Write the pytest tests listed in Section 16 as you go, not at the end.
8. If a requirement is ambiguous, choose the simplest option that keeps the explainability and verifiability features intact, and note the decision in `DECISIONS.md`.

---

## 1. Product summary

### 1.1 Problem
Universities and medical colleges use citation counts to evaluate and promote doctors and researchers. Those counts are often inflated and cannot be verified:
- The same paper exists as multiple records (typos, missing DOI, preprint plus published version), so citations are double counted.
- One citing article may mention a paper many times, and some systems count each mention.
- Citations from the researcher's own college are mixed with independent external citations.
- Reports are plain numbers with no proof, so a promotion committee cannot audit them.

### 1.2 Solution
CiteWise is an AI-assisted (rules-decided, auditable) platform that:
1. Eliminates duplicate paper and citation records.
2. Counts repeated mentions of one paper inside one citing publication as exactly one citation.
3. Classifies every citation as self, internal (same institution), or external.
4. Generates researcher-wise and institution-wise reports in which every number is clickable, traceable to evidence, and verifiable through a hash and QR code.

### 1.3 One-line positioning
"We don't just give a citation number. We give proof."

### 1.4 What makes it stand out (must all be visible in the demo)
| # | Differentiator | Where it appears |
|---|---|---|
| D1 | Audit trail: every number drills down to the citations and the rule that decided them | Researcher page, citation drawer |
| D2 | Verifiable reports: SHA-256 evidence hashes, Merkle root, QR code, public verify page | PDF report, `/verify/[id]` |
| D3 | Raw-vs-verified waterfall chart showing exactly where inflation comes from | Researcher and institution pages |
| D4 | Configurable institutional policy engine (what counts as "internal") with live recompute | `/policy` |
| D5 | Integrity flags: retracted-paper citations, citation rings, abnormal internal ratio | Integrity panel |
| D6 | Human-in-the-loop review queue for uncertain merges (no silent wrong merges) | `/review` |
| D7 | Promotion-ready PDF with verified h-index and internal/external split | Report export |
| D8 | Medical awareness: PubMed/PMC IDs, MeSH topics, publication types, retraction awareness | Paper table, filters |

### 1.5 Non-goals (do not build)
- No user accounts or full authentication (demo mode). Optional single admin token only.
- No patient data of any kind. Public bibliographic data only.
- No claim to replace Google Scholar, Scopus, or Web of Science. CiteWise is a verification layer on top of open data.
- No blockchain. A hash chain / Merkle root is enough.
- No automatic promotion decisions. Output is evidence for humans.

---

## 2. Users and scenarios

| User | Need | Key scenario |
|---|---|---|
| Promotion committee member | Trustworthy, auditable numbers | Opens a candidate's report, clicks "87 verified external", sees each citation and why it counts |
| Institution research admin | Institution-wide view and fair rules | Sets the policy for "internal", views leaderboard and integrity flags |
| Researcher / doctor | A verified record for applications | Views own report, downloads PDF with QR code |
| Data steward | Resolve uncertain data | Works the review queue for duplicate and affiliation matches |
| External verifier | Check a report without trusting CiteWise | Scans the QR code, lands on the verify page, sees hash match status |

---

## 3. Glossary (short; full version in DOCS)

- **Work / paper**: one research publication.
- **Citing work**: the paper that contains the reference.
- **Cited work**: the paper being referenced.
- **Citation (edge)**: one unique pair `(citing_work, cited_work)`. A pair counts once no matter how many times it is mentioned.
- **Mention**: one occurrence of a reference inside the citing paper's text.
- **Canonical work**: the single merged record that represents all duplicate records of a paper.
- **Alias record**: a raw record that was merged into a canonical work.
- **DOI / PMID / PMCID**: identifiers for papers (see DOCS).
- **ROR ID**: unique identifier for an institution.
- **Policy**: institution-specific settings that define "internal" and thresholds.
- **Evidence record**: JSON snapshot of one citation with its sources and decision reasons, hashed with SHA-256.

---

## 4. Domain model summary

```
Institution (ROR)  1 ──── n  Authorship  n ──── 1  Author
                                │
                                n
                               Work (canonical)  1 ──── n  WorkAlias (raw duplicate records)
                                │
                  citing ───────┴─────── cited
                                │
                            Citation (unique edge)  1 ──── n  Mention
                                │
                                ├── Classification (self | internal | external) per scope + policy
                                └── Evidence (JSON + sha256)

Report (researcher | institution) ── root_hash ── verify page + QR
ReviewItem (dedup | affiliation) ── human decisions
IntegrityFlag
```

---

## 5. Counting and classification rules (authoritative spec)

These rules define correctness. Implement exactly, with tests.

### 5.1 Identity normalization
- **DOI normalize**: lowercase; strip `https://doi.org/`, `http://dx.doi.org/`, `doi:` prefixes; trim whitespace and trailing punctuation.
- **PMID**: digits only. **PMCID**: uppercase `PMC` + digits.
- **Title normalize**: Unicode NFKD, remove diacritics, lowercase, replace punctuation with a space, collapse whitespace, normalize British/American spelling variants via a small mapping table (`randomised→randomized`, `tumour→tumor`, `haemoglobin→hemoglobin`, `oesophag→esophag`, etc.).
- **Author key**: normalized last name + first initial. Prefer OpenAlex author ID or ORCID when present.

### 5.2 Duplicate elimination (cascade, first match wins)
| Level | Rule | Action |
|---|---|---|
| L1 | Same normalized DOI, or same PMID, or same PMCID | Auto-merge (reason `exact_id`, confidence 1.0) |
| L2 | Same hash of `title_norm + year + first_author_lastname` | Auto-merge (reason `title_year_author_hash`, confidence 0.97) |
| L3 | Blocked candidates (same first-author surname and year within ±1) with `rapidfuzz.fuzz.token_set_ratio(title_a_norm, title_b_norm) >= policy.dedup_auto_threshold` (default 92) AND year diff ≤ 1 AND at least one shared author surname | Auto-merge (reason `fuzzy_title`, confidence = score/100) |
| L4 | Score between `dedup_review_min` (default 80) and the auto threshold, OR the preprint rule applies below | Send to review queue, do not merge |
| Guard | "Different part" guard: extract numeric tokens and roman numerals and tokens such as `part`, `phase`, `trial 1/2`; if the sets differ between two titles, never auto-merge (send to review) | Prevents merging "Part 1" and "Part 2" |
| Preprint rule | One record's source is a preprint server (medRxiv, bioRxiv, SSRN, arXiv) and the other is a journal article, title score ≥ 95, author overlap ≥ 50%, year diff ≤ 2 | Auto-merge as `preprint_to_published`, mark preprint as alias |

Every merge writes a `work_aliases` row with `merge_reason`, `merge_confidence`, `status` (`auto`, `review_pending`, `approved`, `rejected`). Rejected review items must permanently block re-merging that pair.

Canonical record selection: prefer the record with a DOI, then PMID, then most complete metadata, then earliest retrieval.

### 5.3 Citation edge uniqueness
- After canonicalization, a citation is the pair `(citing_canonical_id, cited_canonical_id)`.
- Database constraint: `UNIQUE (citing_work_id, cited_work_id)`.
- A work can never cite itself (CHECK `citing_work_id <> cited_work_id`).
- `mention_count` stores how many in-text mentions exist. It never changes the citation count.

### 5.4 Raw-to-verified waterfall (exact arithmetic)
The raw import table `raw_citation_rows` holds citation rows exactly as received. Each row has a `raw_citing_record_id`, `raw_cited_record_id`, and `row_kind` (`reference_entry` or `mention`).

For every canonical pair `(C, P)`, take all raw rows that resolve to it. Let:
- `primary_record` = the raw citing record chosen as canonical for C (Section 5.2).
- `rows_total` = number of raw rows in the group.
- `rows_primary` = rows whose citing record is the primary record.
- `duplicates_removed(group) = rows_total − rows_primary` (rows contributed by alias citing records).
- `repeats_removed(group) = rows_primary − 1` (extra rows from the same citing publication).

Waterfall for any scope (researcher or institution):

```
raw_rows                = sum(rows_total)
− duplicates_removed    = sum(duplicates_removed)
− repeated_mentions     = sum(repeats_removed)
= unique_citations      (== number of distinct citation edges)
− self_citations
− internal_citations
= verified_external     (headline number by default)
```

Invariants (must be asserted in code and tests):
- `raw_rows − duplicates_removed − repeated_mentions == unique_citations`
- `unique_citations == self + internal + external`

### 5.5 Classification (per scope)
Classification depends on the report scope.

**Researcher scope** (subject researcher R, cited paper P authored by R, citing paper C):
1. `self` if R is among the authors of C (matched by OpenAlex author ID or ORCID; fall back to name match with review flag).
2. Else `internal` if any considered author of C has an institution that equals any institution R was affiliated with on P (compare ROR IDs).
3. Else `external`.

**Institution scope** (institution I):
- Cited paper P counts for I if at least one author of P is affiliated with I on P.
- `self` if the citing paper C shares at least one author with P.
- Else `internal` if at least one considered author of C is affiliated with I.
- Else `external`.

**Paper scope** (no subject): `self` if authors(C) ∩ authors(P) ≠ ∅; `internal` if institutions(C) ∩ institutions(P) ≠ ∅; else `external`.

Affiliations are taken as listed on the paper at publication time, never the author's current institution.

Each classification stores a `reason` JSON, for example:
```json
{
  "rule": "internal_shared_institution",
  "matched_ror": "https://ror.org/02dwcqs71",
  "citing_author": "A. Sharma",
  "cited_author": "R. Gupta",
  "policy_id": 1,
  "policy_version": 3
}
```

### 5.6 Policy configuration (JSON on `policies.config`)
```json
{
  "citing_authors_considered": "any",
  "self_citation_scope": "author",
  "headline_metric": "external_only",
  "dedup_auto_threshold": 92,
  "dedup_review_min": 80,
  "ring_min_mutual_citations": 4,
  "internal_ratio_flag_threshold": 0.5,
  "concentration_flag_threshold": 0.4
}
```
Allowed values:
- `citing_authors_considered`: `any` | `first_last`
- `self_citation_scope`: `author` (the subject only) | `any_shared_author` (any co-author overlap)
- `headline_metric`: `external_only` | `external_plus_internal`

Changing a policy must recompute classifications and report numbers live, and must bump `policy_version`.

### 5.7 Metrics
- `total_verified` per `headline_metric`.
- Verified h-index: largest h such that h papers each have at least h verified citations (using the headline metric).
- i10 index with verified counts.
- Citations per year (timeline), top citing institutions and countries, internal ratio = internal / unique, self ratio = self / unique.
- Raw h-index (from raw counts) shown beside verified h-index for comparison.

### 5.8 Integrity flags
| Flag | Rule |
|---|---|
| `cites_retracted` | A citing paper cites a work where `is_retracted = true`, or a researcher's own paper is retracted |
| `high_internal_ratio` | internal / unique ≥ `internal_ratio_flag_threshold` for the researcher (needs ≥ 10 unique citations) |
| `citation_concentration` | top 3 citing authors account for ≥ `concentration_flag_threshold` of the researcher's unique citations |
| `citation_ring` | A set of 3–6 authors where every pair has mutual citations ≥ `ring_min_mutual_citations`. Use `networkx` on an author-to-author citation digraph, find dense strongly connected components |

Flags are signals, not accusations. Use neutral wording ("worth reviewing"). Each flag has a drill-down with the underlying evidence.

---

## 6. Features and acceptance criteria

### P0 — must work in the demo
| ID | Feature | Acceptance criteria |
|---|---|---|
| F1 | Ingest (cached OpenAlex data + CSV upload) | Load the demo institution in under 30 seconds from cache; CSV upload validates columns and reports row errors |
| F2 | Deduplication with merge log | All planted duplicates in the demo set are merged or queued; merge log visible; Part 1/Part 2 titles are never auto-merged |
| F3 | Mention collapse | A pair with 7 mentions shows `citations = 1`, `mentions = 7` |
| F4 | Self / internal / external classification | Matches ground truth in tests; reason JSON visible in UI |
| F5 | Researcher report page | KPIs, waterfall, paper table with expandable citations, timeline, citing institutions |
| F6 | Institution report page | KPIs, researcher leaderboard, waterfall, internal vs external split |
| F7 | Audit drill-down | Clicking any number opens the list of underlying citations with source link, context sentence, rule, hash |
| F8 | Verifiable report | Report has root hash; PDF shows root hash and QR; verify page recomputes and shows MATCH or MISMATCH |
| F9 | Raw-vs-verified waterfall | Arithmetic satisfies invariants in 5.4 |

### P1 — build if P0 is complete
| ID | Feature | Acceptance criteria |
|---|---|---|
| F10 | Policy editor with live recompute | Switching `citing_authors_considered` changes at least one classification in the demo and the numbers update |
| F11 | Review queue | Approve or reject duplicate candidates side by side; decisions persist and update counts |
| F12 | Integrity flags panel | At least `cites_retracted` and `high_internal_ratio` implemented, with drill-down |
| F13 | PDF report | One-page researcher PDF with root hash and QR |

### P2 — stretch
| ID | Feature |
|---|---|
| F14 | Citation network graph (`react-force-graph-2d`) colored by self/internal/external |
| F15 | Citation ring detection |
| F16 | MeSH / publication-type filters (RCT, meta-analysis, case report) |
| F17 | Optional LLM suggestions for review queue items (off by default) |
| F18 | Live ingest by OpenAlex author ID or ORCID with progress stepper |

Cut order if short on time: F17, F18, F16, F15, F14, F13. Never cut F7, F8, F9.

---

## 7. System architecture

```
┌──────────────┐   JSON/REST   ┌───────────────────┐    SQL     ┌────────────┐
│  Next.js UI  │ ───────────▶ │  FastAPI backend   │ ────────▶ │ PostgreSQL │
│  (TypeScript)│ ◀─────────── │  (Python services) │ ◀──────── │            │
└──────────────┘               └─────────┬─────────┘            └────────────┘
                                         │ (fetch scripts / optional live ingest)
                          ┌──────────────┼──────────────┬───────────────┐
                          ▼              ▼              ▼               ▼
                      OpenAlex     Europe PMC      Crossref           ROR
                       (works,     (full text      (DOI, retraction   (institution
                       citations)   XML)            info)              lookup)
                          │
                    disk cache (JSON) ──▶ OFFLINE_MODE demo
```

Pipeline order: **Ingest → Normalize → Deduplicate → Resolve institutions → Build edges and mentions → Classify → Metrics and flags → Evidence and hashing → Reports**.

---

## 8. Tech stack

### 8.1 Backend (Python 3.11+)
| Purpose | Library / tool |
|---|---|
| API framework | `fastapi`, `uvicorn[standard]` |
| Validation / settings | `pydantic` v2, `pydantic-settings` |
| ORM / DB | `sqlalchemy` 2.x, `psycopg[binary]` (v3), optional `alembic` (can use `create_all` for the hackathon) |
| HTTP client | `httpx` (async), `tenacity` for retries |
| Data processing | `pandas` |
| Fuzzy matching | `rapidfuzz` |
| Text normalization | `unidecode` or `unicodedata`, `regex` |
| Full-text XML parsing | `lxml` |
| Sentence splitting | `pysbd` |
| Graph analysis | `networkx` |
| Hashing | `hashlib` (SHA-256), `json` canonical dumps |
| QR code | `qrcode[pil]` |
| PDF | `jinja2` + `weasyprint` (Linux/Docker). Fallback: `reportlab`, or the frontend print page |
| BibTeX import | `bibtexparser` |
| Testing | `pytest`, `pytest-asyncio`, `httpx` test client |
| Lint / format | `ruff` |
| Optional LLM | `anthropic` SDK (feature F17 only, off by default) |

### 8.2 Frontend (TypeScript)
| Purpose | Library |
|---|---|
| Framework | Next.js (App Router), React, TypeScript |
| Styling | Tailwind CSS, `shadcn/ui` (Radix primitives), `lucide-react` icons |
| Data fetching | `@tanstack/react-query` |
| Tables | `@tanstack/react-table` |
| Charts | `recharts` (waterfall as stacked bar with transparent base, bars, lines, donuts) |
| Network graph | `react-force-graph-2d` (P2) |
| QR on page | `qrcode.react` |
| Animations | `framer-motion` (pipeline stepper, number transitions) |
| Forms / validation | `react-hook-form`, `zod` |
| Theming | `next-themes` |
| Client-side hash verify | Web Crypto API `crypto.subtle.digest('SHA-256', ...)` |

### 8.3 Infrastructure
| Purpose | Choice |
|---|---|
| Database | PostgreSQL (Supabase or Neon free tier, or local Docker). SQLite is acceptable only as an emergency fallback |
| Local dev | `docker-compose.yml` with `postgres`, `backend`, `frontend` |
| Deploy | Frontend on Vercel; backend on Render or Railway; or run everything locally from Docker for the demo |
| Secrets | `.env` files, never committed |

Choose the team's fastest option where a choice exists. Do not pin guessed versions in this document; install the latest stable and then freeze with `pip freeze` / `package-lock.json`.

---

## 9. Repository structure

```
citewise/
├── README.md
├── DECISIONS.md
├── docker-compose.yml
├── .env.example
├── docs/
│   ├── CiteWise_PRD.md
│   └── CiteWise_DOCS.md
├── backend/
│   ├── pyproject.toml  (or requirements.txt)
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models.py            # SQLAlchemy models
│   │   ├── schemas.py           # Pydantic response/request models
│   │   ├── routers/
│   │   │   ├── ingest.py
│   │   │   ├── researchers.py
│   │   │   ├── institutions.py
│   │   │   ├── citations.py
│   │   │   ├── reports.py
│   │   │   ├── verify.py
│   │   │   ├── review.py
│   │   │   ├── policy.py
│   │   │   └── integrity.py
│   │   ├── services/
│   │   │   ├── clients/
│   │   │   │   ├── openalex.py
│   │   │   │   ├── europepmc.py
│   │   │   │   ├── crossref.py
│   │   │   │   └── ror.py
│   │   │   ├── normalize.py
│   │   │   ├── dedup.py
│   │   │   ├── mentions.py
│   │   │   ├── edges.py
│   │   │   ├── classify.py
│   │   │   ├── metrics.py
│   │   │   ├── integrity.py
│   │   │   ├── evidence.py      # canonical JSON, sha256, merkle root
│   │   │   ├── waterfall.py
│   │   │   └── report_pdf.py
│   │   └── templates/report.html
│   ├── scripts/
│   │   ├── fetch_demo_data.py   # pulls from APIs into data/cache
│   │   ├── make_messy_data.py   # plants duplicates/mentions, writes ground_truth.json
│   │   └── seed_db.py           # loads cached data and runs the full pipeline
│   ├── data/
│   │   ├── cache/               # raw API JSON (committed for demo safety)
│   │   └── demo/                # messy dataset + ground_truth.json
│   └── tests/
└── frontend/
    ├── package.json
    ├── app/
    │   ├── page.tsx                         # overview
    │   ├── ingest/page.tsx
    │   ├── institutions/[id]/page.tsx
    │   ├── researchers/[id]/page.tsx
    │   ├── review/page.tsx
    │   ├── policy/page.tsx
    │   └── verify/[reportId]/page.tsx       # public
    ├── components/
    │   ├── WaterfallChart.tsx
    │   ├── KpiCard.tsx
    │   ├── CitationDrawer.tsx               # evidence view
    │   ├── PaperTable.tsx
    │   ├── ClassBadge.tsx
    │   ├── IntegrityPanel.tsx
    │   ├── PipelineStepper.tsx
    │   ├── MergeCompare.tsx
    │   ├── HashVerifier.tsx
    │   └── NetworkGraph.tsx
    └── lib/ (api client, types, format helpers)
```

---

## 10. Data model (PostgreSQL)

```sql
CREATE TABLE institutions (
  id            BIGSERIAL PRIMARY KEY,
  ror_id        TEXT UNIQUE,              -- e.g. https://ror.org/02dwcqs71
  openalex_id   TEXT UNIQUE,
  name          TEXT NOT NULL,
  country_code  TEXT,
  aliases       JSONB DEFAULT '[]'
);

CREATE TABLE authors (
  id            BIGSERIAL PRIMARY KEY,
  openalex_id   TEXT UNIQUE,
  orcid         TEXT,
  display_name  TEXT NOT NULL,
  name_key      TEXT                       -- normalized lastname + initial
);

CREATE TABLE works (                        -- canonical papers
  id            BIGSERIAL PRIMARY KEY,
  openalex_id   TEXT UNIQUE,
  doi           TEXT,
  pmid          TEXT,
  pmcid         TEXT,
  title         TEXT NOT NULL,
  title_norm    TEXT NOT NULL,
  year          INT,
  venue         TEXT,
  pub_type      TEXT,                      -- article, review, preprint...
  is_preprint   BOOLEAN DEFAULT FALSE,
  is_retracted  BOOLEAN DEFAULT FALSE,
  mesh_terms    JSONB DEFAULT '[]',
  source        TEXT,                      -- openalex | csv | pubmed
  retrieved_at  TIMESTAMPTZ DEFAULT now(),
  is_synthetic  BOOLEAN DEFAULT FALSE
);
CREATE UNIQUE INDEX works_doi_uq  ON works(doi)  WHERE doi  IS NOT NULL;
CREATE UNIQUE INDEX works_pmid_uq ON works(pmid) WHERE pmid IS NOT NULL;

CREATE TABLE work_aliases (                 -- raw records merged into a canonical work
  id               BIGSERIAL PRIMARY KEY,
  work_id          BIGINT REFERENCES works(id),
  raw_record_id    TEXT NOT NULL,
  raw_title        TEXT,
  raw_doi          TEXT,
  source           TEXT,
  merge_reason     TEXT,                   -- exact_id | title_year_author_hash | fuzzy_title | preprint_to_published | manual
  merge_confidence NUMERIC(4,3),
  fuzzy_score      NUMERIC(5,2),
  status           TEXT DEFAULT 'auto',    -- auto | review_pending | approved | rejected
  is_synthetic     BOOLEAN DEFAULT FALSE
);

CREATE TABLE authorships (
  id              BIGSERIAL PRIMARY KEY,
  work_id         BIGINT REFERENCES works(id),
  author_id       BIGINT REFERENCES authors(id),
  institution_id  BIGINT REFERENCES institutions(id),   -- nullable if unresolved
  position        TEXT,                    -- first | middle | last
  raw_affiliation TEXT
);
CREATE INDEX authorships_work_idx ON authorships(work_id);
CREATE INDEX authorships_author_idx ON authorships(author_id);
CREATE INDEX authorships_inst_idx ON authorships(institution_id);

CREATE TABLE raw_citation_rows (            -- citation rows exactly as received
  id                   BIGSERIAL PRIMARY KEY,
  raw_citing_record_id TEXT NOT NULL,
  raw_cited_record_id  TEXT NOT NULL,
  row_kind             TEXT NOT NULL,      -- reference_entry | mention
  context_sentence     TEXT,
  section              TEXT,
  source               TEXT,
  is_synthetic         BOOLEAN DEFAULT FALSE
);

CREATE TABLE citations (                    -- unique edges
  id               BIGSERIAL PRIMARY KEY,
  citing_work_id   BIGINT NOT NULL REFERENCES works(id),
  cited_work_id    BIGINT NOT NULL REFERENCES works(id),
  mention_count    INT NOT NULL DEFAULT 1,
  raw_rows_total   INT NOT NULL,
  duplicates_removed INT NOT NULL DEFAULT 0,
  repeats_removed  INT NOT NULL DEFAULT 0,
  UNIQUE (citing_work_id, cited_work_id),
  CHECK (citing_work_id <> cited_work_id)
);

CREATE TABLE mentions (
  id           BIGSERIAL PRIMARY KEY,
  citation_id  BIGINT REFERENCES citations(id),
  sentence     TEXT,
  section      TEXT,
  source       TEXT,                       -- europepmc_fulltext | csv | synthetic
  is_synthetic BOOLEAN DEFAULT FALSE
);

CREATE TABLE policies (
  id           BIGSERIAL PRIMARY KEY,
  institution_id BIGINT REFERENCES institutions(id),
  name         TEXT,
  version      INT DEFAULT 1,
  config       JSONB NOT NULL,
  is_active    BOOLEAN DEFAULT TRUE
);

CREATE TABLE citation_classifications (
  id             BIGSERIAL PRIMARY KEY,
  citation_id    BIGINT REFERENCES citations(id),
  scope_type     TEXT NOT NULL,            -- researcher | institution | paper
  scope_id       BIGINT,                   -- author_id or institution_id
  policy_id      BIGINT REFERENCES policies(id),
  policy_version INT,
  klass          TEXT NOT NULL,            -- self | internal | external
  reason         JSONB NOT NULL,
  UNIQUE (citation_id, scope_type, scope_id, policy_id, policy_version)
);

CREATE TABLE evidence (
  id            BIGSERIAL PRIMARY KEY,
  citation_id   BIGINT REFERENCES citations(id),
  scope_type    TEXT, scope_id BIGINT,
  record        JSONB NOT NULL,            -- canonical evidence JSON
  sha256        TEXT NOT NULL,
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE reports (
  id            BIGSERIAL PRIMARY KEY,
  scope_type    TEXT NOT NULL,             -- researcher | institution
  scope_id      BIGINT NOT NULL,
  policy_id     BIGINT REFERENCES policies(id),
  policy_version INT,
  payload       JSONB NOT NULL,            -- full report incl. evidence snapshot
  root_hash     TEXT NOT NULL,
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE review_items (
  id            BIGSERIAL PRIMARY KEY,
  item_type     TEXT NOT NULL,             -- dedup | affiliation | author
  payload       JSONB NOT NULL,            -- both records, score, reasons
  score         NUMERIC(5,2),
  status        TEXT DEFAULT 'pending',    -- pending | approved | rejected
  decided_at    TIMESTAMPTZ
);

CREATE TABLE rejected_merges (
  raw_record_a TEXT, raw_record_b TEXT,
  PRIMARY KEY (raw_record_a, raw_record_b)
);

CREATE TABLE integrity_flags (
  id          BIGSERIAL PRIMARY KEY,
  flag_type   TEXT NOT NULL,
  scope_type  TEXT, scope_id BIGINT,
  severity    TEXT,                        -- info | review
  details     JSONB NOT NULL
);
```

---

## 11. Pipeline specification

### 11.1 Ingest
- `fetch_demo_data.py` (run once, before the hackathon, with network): given a ROR ID or a list of OpenAlex author IDs, fetch each author's works, then for each work fetch all citing works. Save every raw API response under `data/cache/` keyed by a hash of the URL. Commit the cache.
- OpenAlex request pattern for citing works: `GET /works?filter=cites:{WORK_ID}&per-page=200&cursor=*&select=id,doi,title,publication_year,authorships,ids,type,is_retracted,primary_location`. Page with the cursor until exhausted.
- **OpenAlex now requires a free API key** (the old `mailto` polite pool was replaced in 2026 and usage is metered against a daily budget). Read `OPENALEX_API_KEY` from env, send it as the docs specify, cache everything, and fetch the demo data well before the demo.
- CSV upload (P0) columns: `citing_title, citing_doi, citing_year, citing_authors, citing_affiliations, cited_title, cited_doi, cited_year, cited_authors, context_sentence`. Validate, report row-level errors, load into `raw_citation_rows` and works.

### 11.2 Normalize
Implement Section 5.1 functions in `normalize.py` with unit tests.

### 11.3 Deduplicate (`dedup.py`)
- Build candidate blocks by `(first_author_surname, year)`, widening to year ±1 to avoid O(n²) comparisons.
- Run L1, L2, L3, L4, the guard, and the preprint rule from Section 5.2.
- Use `rapidfuzz.fuzz.token_set_ratio` on normalized titles. Optionally `process.extract` with `score_cutoff=80`.
- Write `work_aliases` rows. Check `rejected_merges` before merging.
- Return a summary: counts by reason, queued items.

### 11.4 Resolve institutions
- Prefer ROR IDs supplied by OpenAlex authorships.
- For CSV data or unresolved raw affiliation strings, call ROR's affiliation matching (`https://api.ror.org/v2/organizations?affiliation=...`) in cached/batched form and use the result flagged `chosen: true` only; lower confidence results go to the review queue as `affiliation` items.
- Keep a small alias table for the demo institution(s) to make offline mode deterministic.

### 11.5 Build edges and mentions (`edges.py`, `mentions.py`)
- Resolve every raw row to canonical work IDs, group by pair, and compute `raw_rows_total`, `duplicates_removed`, `repeats_removed` per Section 5.4. Insert into `citations`.
- Mentions: for open-access papers with a PMCID, fetch Europe PMC full-text XML (JATS). Find `<xref ref-type="bibr" rid="...">` in the body; look up the matching `<ref id="...">` in `<ref-list>` and read its `pub-id` DOI/PMID; match to the cited work by DOI/PMID, falling back to title fuzzy match. Take the enclosing `<p>`, split into sentences with `pysbd`, and keep the sentence containing the xref. Record the nearest ancestor `<sec><title>` as `section`.
- If no full text is available, create one mention row with a null sentence (source `reference_list`).

### 11.6 Classify (`classify.py`)
Implement Section 5.5 as a pure function:
```python
def classify(citing: WorkView, cited: WorkView, scope: Scope, policy: Policy) -> tuple[str, dict]:
    """Returns ('self'|'internal'|'external', reason_dict). Deterministic, no I/O."""
```
`WorkView` contains authors (with IDs and positions) and institution ROR IDs.

### 11.7 Metrics and integrity (`metrics.py`, `integrity.py`)
Implement Sections 5.7 and 5.8. Metrics are computed from classification rows plus the policy's `headline_metric`.

### 11.8 Optional LLM assist (F17, off by default)
- Env flag `ENABLE_LLM_ASSIST=false`. When true, for review items only, call the model with both records and ask for strict JSON `{"same_paper": bool, "confidence": 0-1, "reason": str}`. Show the suggestion in the review UI as "AI suggestion", never auto-apply.
- Default model name from env `LLM_MODEL` (default `claude-sonnet-5-5`).

### 11.9 Evidence and hashing (`evidence.py`)
Evidence record for one citation in one scope:
```json
{
  "citation_id": 1042,
  "scope": {"type": "researcher", "id": 7},
  "citing": {"doi": "10.1000/abc", "pmid": "123", "title": "...", "year": 2022, "authors": ["..."], "institutions": ["https://ror.org/..."]},
  "cited":  {"doi": "10.1000/xyz", "title": "...", "year": 2019},
  "mention_count": 7,
  "raw_rows_total": 9,
  "duplicates_removed": 1,
  "repeats_removed": 6,
  "class": "external",
  "reason": {"rule": "no_shared_institution"},
  "policy": {"id": 1, "version": 3},
  "sources": [{"name": "openalex", "retrieved_at": "2026-10-10T08:00:00Z"}],
  "links": {"citing": "https://doi.org/10.1000/abc", "cited": "https://doi.org/10.1000/xyz"},
  "context_sentences": ["..."]
}
```
Hashing rules (must be identical in backend and in the browser verifier):
1. Canonical JSON: keys sorted, no extra whitespace, UTF-8: `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
2. Leaf hash = `sha256(canonical_json).hexdigest()`.
3. Sort leaves by `citation_id` ascending.
4. Merkle root: repeatedly hash the concatenation of two adjacent hex strings with SHA-256; if a level has an odd count, duplicate the last hash.
5. `root_hash` is stored on the report and printed on the PDF, with the QR pointing to `/verify/{report_id}`.

Honest limitation (state it in the UI and the pitch): the hash proves a report was not altered after generation and shows where each record came from. It does not prove the upstream databases are correct, which is why every record links to the original DOI.

### 11.10 Reports (`report_pdf.py`, `reports.py`)
Report payload fields: subject, policy snapshot, KPIs, waterfall, per-paper table, per-citation evidence list, integrity flags, generated_at, data sources and retrieval dates, synthetic-data disclosure if any, `root_hash`.
PDF: Jinja2 template, single page summary plus appendix pages listing citations. Include QR (PNG data URI) and the root hash text. If WeasyPrint cannot be installed, use the frontend print-optimized route `/researchers/[id]/print` with a print stylesheet.

---

## 12. API specification (REST, JSON, prefix `/api`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| POST | `/ingest/demo` | Load cached demo data and run the full pipeline; returns step summaries |
| POST | `/ingest/csv` | Upload CSV, validate, load, run pipeline |
| POST | `/ingest/live` | (P2) Start live fetch by author ID or ORCID; returns job id |
| GET | `/ingest/jobs/{id}` | Pipeline step progress for the stepper UI |
| GET | `/institutions` | List institutions |
| GET | `/institutions/{id}/report` | Institution report (query: `policy_id`) |
| GET | `/institutions/{id}/researchers` | Leaderboard rows |
| GET | `/researchers/{id}/report` | Researcher report (query: `policy_id`) |
| GET | `/researchers/{id}/papers` | Paper table with counts |
| GET | `/papers/{id}/citations` | Citations for a paper (query: `scope`, `class`) |
| GET | `/citations/{id}/evidence` | Full evidence record with sha256 |
| GET | `/waterfall` | Query: `scope_type`, `scope_id`, `policy_id` |
| GET | `/policies` / POST `/policies` / PUT `/policies/{id}` | Read and update policy; PUT recomputes and bumps version |
| GET | `/review` | List pending review items |
| POST | `/review/{id}/decision` | Body `{ "decision": "approve" | "reject" }`; recomputes affected counts |
| GET | `/integrity` | Query: `scope_type`, `scope_id` |
| POST | `/reports` | Body `{scope_type, scope_id, policy_id}`; generates and stores a report with root hash |
| GET | `/reports/{id}` | Report JSON |
| GET | `/reports/{id}/pdf` | PDF download |
| GET | `/verify/{report_id}` | Public. Recomputes leaf hashes and root from stored payload; returns `{stored_root, recomputed_root, status: "MATCH"|"MISMATCH", generated_at, record_count}` |

Standard error shape: `{ "error": { "code": "string", "message": "string" } }`. Use pagination (`page`, `page_size`) on list endpoints.

### 12.1 Researcher report response (shape)
```json
{
  "researcher": {"id": 7, "name": "Dr. Example", "orcid": null, "institutions": ["..."]},
  "policy": {"id": 1, "version": 3, "headline_metric": "external_only"},
  "kpis": {
    "papers": 42,
    "raw_rows": 142,
    "unique_citations": 101,
    "self": 15, "internal": 21, "external": 65,
    "verified_total": 65,
    "h_index_raw": 9, "h_index_verified": 7, "i10_verified": 4,
    "internal_ratio": 0.21, "self_ratio": 0.15
  },
  "waterfall": [
    {"label": "Raw rows", "value": 142},
    {"label": "Duplicate records removed", "value": -21},
    {"label": "Repeated mentions collapsed", "value": -20},
    {"label": "Unique citations", "value": 101, "subtotal": true},
    {"label": "Self-citations", "value": -15},
    {"label": "Internal citations", "value": -21},
    {"label": "Verified external", "value": 65, "total": true}
  ],
  "timeline": [{"year": 2021, "external": 10, "internal": 4, "self": 2}],
  "top_citing_institutions": [{"name": "...", "ror": "...", "count": 7}],
  "integrity_flags": [],
  "data_notice": {"has_synthetic": true, "synthetic_rows": 340}
}
```
(Numbers above are illustrative only. The real values come from the database.)

---

## 13. Frontend specification

### 13.1 Design direction
Clean, trustworthy, academic-medical: light background, teal/indigo accent, one neutral gray scale, clear typography (e.g. Inter), generous whitespace, dark mode via `next-themes`. Class colors are consistent everywhere: self = amber, internal = indigo, external = teal. Never rely on color alone: use text labels in badges.

### 13.2 Pages
1. **Overview `/`**: institution selector, hero statement, "Load demo data" button, headline KPIs (raw vs verified), links to the researcher leaderboard.
2. **Ingest `/ingest`**: CSV upload and "Load demo" action. `PipelineStepper` shows the 9 pipeline stages with live status and counts (for example "Duplicates merged: 23, queued for review: 4").
3. **Institution `/institutions/[id]`**: KPI cards, waterfall, internal vs external stacked bar by year, researcher leaderboard table (sortable; raw vs verified columns), integrity panel, "Generate report" button.
4. **Researcher `/researchers/[id]`**: KPI cards, **waterfall chart**, paper table (expand a row to see citations), timeline, top citing institutions, integrity panel, "Generate verified report" button. Every KPI and every waterfall bar is clickable and opens the `CitationDrawer` filtered to that number.
5. **Review `/review`**: side-by-side `MergeCompare` (title diff highlighted, DOI, year, authors, similarity score), Approve / Reject buttons, optional AI suggestion chip.
6. **Policy `/policy`**: form controls for each policy option, a "preview impact" panel showing before/after numbers, Save to apply and recompute.
7. **Verify `/verify/[reportId]`** (public, no navigation chrome needed): big MATCH / MISMATCH status, stored vs recomputed root hash, record count, generated date, data-source list, and `HashVerifier`: a box to paste the report JSON and recompute the root hash in the browser with Web Crypto.

### 13.3 Key components
- **WaterfallChart**: Recharts `BarChart` with an invisible base series and a visible delta series; color: totals teal, removals gray-red, subtotal indigo; labels show values; clicking a bar opens the drawer with the corresponding rows.
- **CitationDrawer**: lists citations; each item shows citing title and year, class badge, mention count ("7 mentions → counted once"), context sentence, source links (DOI), the reason JSON rendered as plain English, and the evidence hash with a copy button.
- **ClassBadge**, **KpiCard** (with raw vs verified comparison), **PaperTable** (TanStack Table), **IntegrityPanel** (neutral language), **PipelineStepper**, **HashVerifier**, **NetworkGraph** (P2).
- Show a persistent small banner when `data_notice.has_synthetic` is true.

### 13.4 UX requirements
- Loading skeletons, empty states, and error toasts on all data views.
- Responsive down to tablet width; desktop-first is acceptable for the demo.
- Numbers animate (count-up) once on load; no heavy animation elsewhere.
- Accessibility: labels on controls, sufficient contrast, keyboard-closable drawer.

---

## 14. Demo data strategy

Goal: show real data and make the cleaning visible and honest.

1. **Real base**: pick one real medical institution (for example a large Indian medical institute) and 5 researchers. Pull their works and the works that cite them with `fetch_demo_data.py` (about 300 papers and their citing works). Cache to disk.
2. **Planted noise** (`make_messy_data.py`, deterministic with `seed=42`, all planted rows flagged `is_synthetic=true`):
   - Duplicate records: for about 20% of works create alias records by removing the DOI, introducing title typos or spelling variants, swapping a colon for a dash, or creating a preprint version.
   - Repeated mentions: for about 30% of citation pairs add 2–7 extra mention rows. Use real Europe PMC mentions where available; mark any invented ones as synthetic.
   - Look-alike traps: at least 3 pairs of titles differing only by "Part 1/Part 2" or trial numbers, to prove the guard works.
   - Integrity demo: optionally add a small synthetic citation ring and one citation to a real retracted work (OpenAlex `is_retracted:true`), flagged synthetic.
3. **Ground truth**: write `ground_truth.json` listing expected merges, expected unique citation counts per researcher, and expected classes for a sample of citations. Tests compare pipeline output with it.
4. **Disclosure**: the UI banner and the PDF footer say the demo includes synthetic noise for demonstration, with the count of synthetic rows. In the pitch: "real OpenAlex data plus deliberately planted errors, so you can see the cleaning work."
5. **Offline**: all demo reads come from `data/cache`. `OFFLINE_MODE=true` blocks outbound HTTP.

---

## 15. Build plan (phases with exit criteria)

Estimated for a 24-hour hackathon with 3–4 people. Parallelize backend and frontend after agreeing on the JSON shapes in Section 12 (first hour).

| Phase | Hours | Backend tasks | Frontend tasks | Exit criteria |
|---|---|---|---|---|
| 0. Setup | 0–2 | Repo, Docker, FastAPI skeleton, DB models, `.env`, `/health` | Next.js + Tailwind + shadcn, API client, layout, mock data matching Section 12.1 | Both apps run; frontend renders from mock JSON |
| 1. Data | 2–5 | `fetch_demo_data.py`, cache, `make_messy_data.py`, `ground_truth.json`, `seed_db.py` loads raw rows | Overview page, ingest page shell | Demo dataset in DB and cache committed |
| 2. Dedup + edges | 5–9 | `normalize.py`, `dedup.py`, `edges.py`, `mentions.py`, waterfall arithmetic | Pipeline stepper wired to job status | Tests T1–T5, T11 pass |
| 3. Classify + metrics | 9–13 | `classify.py`, policies, metrics (h-index, i10), researcher and institution report endpoints | Researcher and institution pages with KPI cards, paper table, timeline | Tests T6–T9, T12 pass; pages show real numbers |
| 4. Audit + verify | 13–17 | Evidence builder, hashing, Merkle root, reports, verify endpoint | Waterfall chart, CitationDrawer, verify page, HashVerifier | Tests T10 pass; clicking numbers opens evidence |
| 5. P1 features | 17–21 | Review queue endpoints, policy PUT recompute, integrity flags, PDF with QR | Review page, policy page, integrity panel, report download | Policy change updates numbers live; PDF has QR |
| 6. Polish + rehearsal | 21–24 | Fix bugs, seed script idempotent, deploy or Docker compose up | Visual polish, empty/error states, demo script rehearsal | Full demo runs end to end twice without errors |

Suggested team roles: (A) data and pipeline, (B) classification, metrics, reports, hashing, (C) frontend pages and charts, (D) pitch, demo script, QA, README. With three people, merge A and B.

---

## 16. Testing and acceptance tests

Write these as pytest tests (backend) and a manual checklist (frontend). Use fixtures built from small hand-made records, plus the `ground_truth.json` integration test.

| ID | Test | Expected |
|---|---|---|
| T1 | DOI normalization: `https://doi.org/10.1038/ABC` vs `10.1038/abc` | Equal after normalize |
| T2 | Two records with the same DOI but different titles | Merged, reason `exact_id` |
| T3 | Titles "Effect of Metformin on Type 2 Diabetes: A Randomized Trial" vs "Effects of metformin on type-2 diabetes. A randomised trial." (same year, shared author) | Auto-merged by fuzzy rule |
| T4 | "...: Part 1" vs "...: Part 2" with similar authors and year | Not merged; one review item created |
| T5 | One citing paper with 7 mention rows of one cited paper | Exactly 1 citation, `mention_count = 7`, `repeats_removed = 6` |
| T6 | Citing paper includes the researcher as author | Class `self` |
| T7 | Citing and cited paper authors differ but share the same ROR ID | Class `internal`, reason names the ROR ID |
| T8 | No shared author or institution | Class `external` |
| T9 | Policy `citing_authors_considered` changed `any → first_last`, where the only institution match is a middle author | Class flips `internal → external` |
| T10 | Generate report, change one evidence record, call verify | Status `MISMATCH`; unmodified report returns `MATCH` |
| T11 | Waterfall invariants on the full demo dataset | Both invariants in Section 5.4 hold for every researcher and institution |
| T12 | h-index on `[10, 8, 5, 4, 3]` | 4 |
| T13 | Rejected merge pair is never auto-merged on a rerun | Stays separate |
| T14 | Integration: run the full pipeline on the demo dataset | Matches `ground_truth.json` for planted duplicates and expected counts |
| T15 | Browser and backend produce the same root hash for the same JSON | Equal |

Frontend manual checklist: waterfall renders and bars click through; drawer shows evidence; policy preview matches saved numbers; verify page shows MATCH for an untouched report; PDF opens and the QR resolves to the verify page.

---

## 17. Non-functional requirements

- **Performance**: report endpoints respond in under 2 seconds on the demo dataset (use SQL aggregation or precomputed classification rows, not Python loops over every citation per request). Pipeline on demo data completes in under 60 seconds.
- **Determinism**: same input and policy always gives the same output and the same hashes. Seed all random generation.
- **Reliability**: all external calls use timeouts and `tenacity` retries with backoff; failures never crash the pipeline (log and continue); HTTP 429 handled with waiting.
- **Security**: no secrets in the repo; CORS restricted to the frontend origin; parameterized queries only (SQLAlchemy); optional `ADMIN_TOKEN` header for write endpoints; verify endpoint is read-only and public.
- **Privacy**: public bibliographic metadata only.
- **Observability**: structured logging with step names and counts; `/ingest/jobs/{id}` exposes progress.
- **Licensing and attribution**: show data source names and retrieval dates in reports. OpenAlex data is CC0; follow terms of the other APIs.

---

## 18. Environment variables (`.env.example`)

```
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/citewise
OFFLINE_MODE=true
OPENALEX_API_KEY=
CROSSREF_MAILTO=you@example.com
NCBI_API_KEY=
FRONTEND_ORIGIN=http://localhost:3000
PUBLIC_BASE_URL=http://localhost:3000        # used for QR code links
ADMIN_TOKEN=
ENABLE_LLM_ASSIST=false
ANTHROPIC_API_KEY=
LLM_MODEL=claude-sonnet-5-5
```
Frontend: `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api`.

---

## 19. Demo script (5 minutes) and pitch

1. (30s) Problem and pitch line: "Citation counts are numbers nobody can verify. CiteWise turns them into auditable records."
2. (45s) Ingest: load the demo data, watch the pipeline stepper report merges and queued items.
3. (60s) Researcher page: show the raw count, then the **waterfall** down to verified external citations.
4. (45s) Click "Repeated mentions collapsed", open a pair with 7 mentions → counted once, show the sentences.
5. (45s) Policy page: switch the internal rule and watch numbers change live.
6. (45s) Click one citation: evidence card with source links, rule, hash.
7. (45s) Generate the report PDF, scan the QR, land on the verify page: MATCH. Mention the tamper test.
8. (15s) Close: limitations (open-data coverage, name disambiguation, full-text mentions only for open-access papers), next steps, and "AI assists, rules decide, everything is auditable".

Jury Q&A and the "how are we different" answers are in `CiteWise_DOCS.md`.

---

## 20. Risks and mitigations

| Risk | Mitigation |
|---|---|
| API rate limits or key requirement mid-demo | Fetch and cache beforehand, commit the cache, run `OFFLINE_MODE=true` |
| Wrong merges | Conservative thresholds, guard rules, review queue, rejected-merge memory |
| Author name ambiguity | Prefer OpenAlex author IDs and ORCID; flag name-only matches for review |
| Missing affiliations | Show unresolved count in the report; never silently classify as external without noting unresolved authors (reason `unresolved_affiliation`) |
| WeasyPrint install problems | Docker/Linux for PDF, or reportlab, or print-CSS page |
| Running out of time | Follow the cut order in Section 6; never cut F7, F8, F9 |
| Perception that synthetic data is fake results | Clear disclosure banner; ground truth file; honest pitch wording |

---

## 21. Definition of done

- All P0 features work end to end on the demo dataset, offline.
- Tests T1–T15 pass (T10 and T15 are mandatory).
- Every number in the UI drills down to evidence.
- A generated report verifies as MATCH and fails as MISMATCH when tampered with.
- README explains setup, seed, run, and test commands in under 10 lines.
- `DECISIONS.md` lists any deviations from this PRD.
