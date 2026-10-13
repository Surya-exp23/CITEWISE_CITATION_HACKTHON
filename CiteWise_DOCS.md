# CiteWise — Project Documentation

Concepts, libraries, datasets, setup, pitch, and jury Q&A.
Companion to `CiteWise_PRD.md` (the build specification). This file explains the *why* and the *what we use*; the PRD explains the *how to build*.

---

## Table of contents
1. Project in plain words
2. Concepts explained simply (citation, DOI, PMID, PMCID, ROR, etc.)
3. Fuzzy matching and the RapidFuzz score
4. Hashing and verification in plain words
5. Libraries and tools (with install commands)
6. Data sources and datasets (with links and example calls)
7. How we build the demo dataset
8. How CiteWise is different (positioning)
9. 30-second pitch and 5-minute story
10. Jury Q&A (with model answers)
11. Honest limitations (say these before they ask)
12. Day-before checklist and team roles
13. Quick command cheat sheet

---

## 1. Project in plain words

Universities promote doctors and researchers partly on how many times their papers are cited. Those numbers are often **inflated** and **unverifiable**:

- The same paper is stored twice, so it gets counted twice.
- One article mentions your paper seven times, and some systems count seven citations.
- A colleague from your own college cites you, and it is counted the same as a stranger's citation.
- The final report is just a number with no proof.

**CiteWise cleans the data, applies fair counting rules, separates self, internal, and external citations, and produces reports where every number can be clicked, traced to its source, and verified with a hash and QR code.**

Core idea: **"We don't just give a number. We give proof."**

---

## 2. Concepts explained simply

### 2.1 Research paper, citation, mention
- A **paper** (work) is a published piece of research.
- A **citation** happens when Paper B lists Paper A in its references. B is the *citing* paper; A is the *cited* paper. A's authors get +1 citation.
- A **mention** is each time B talks about A in its text ("as shown by Smith et al. [12]..."). B may mention A many times but still cites it once.

Think of citations as recommendation letters: if 100 independent people vouch for your work, that signals impact.

### 2.2 Paper IDs
| ID | Meaning | Who issues it | Example | Notes |
|---|---|---|---|---|
| DOI | Digital Object Identifier | Publishers (via Crossref and others) | `10.1038/s41586-020-2649-2` | Works for any field; the best ID for deduplication. Always normalize: lowercase, remove `https://doi.org/` |
| PMID | PubMed ID | PubMed (US National Library of Medicine) | `32939066` | Only for medical and life-science papers |
| PMCID | PubMed Central ID | PubMed Central (free full-text archive) | `PMC7523456` | Exists only if free full text is available; this is what lets us count mentions inside the paper |
| OpenAlex ID | Internal ID in OpenAlex | OpenAlex | `W2626778328` (works), `A5023888391` (authors), `I136199984` (institutions) | Our main data source's IDs |
| ORCID | Researcher ID | ORCID | `0000-0002-1825-0097` | Unique ID for a person, helps tell apart researchers with the same name |

Analogy: IDs are like Aadhaar numbers for papers. Names and titles can be written differently, IDs identify the exact paper.

### 2.3 ROR ID (Research Organization Registry)
A unique ID for every university, hospital, or research institute, for example `https://ror.org/02dwcqs71`.

Why it matters: authors write their college in many ways ("AIIMS, New Delhi", "All India Institute of Medical Sciences", "Dept. of Cardiology, AIIMS Delhi, India"). A computer sees three different strings. ROR gives all three one ID, so "same college?" becomes a simple ID comparison. OpenAlex already provides ROR IDs for most affiliations.

### 2.4 The three citation types
| Type | Meaning |
|---|---|
| **Self-citation** | The same author is on both papers |
| **Internal** | Different people, same institution |
| **External** | Different institutions: the most independent evidence of impact |

We do not delete internal or self citations. We separate them so a committee sees all numbers and decides how to weigh them.

### 2.5 Other terms
- **h-index**: the largest number h such that h papers each have at least h citations. Example: citations `[10, 8, 5, 4, 3]` give h = 4.
- **i10-index**: the number of papers with at least 10 citations.
- **Verified h-index**: the h-index computed using only verified citations (after cleaning and per the policy's headline metric).
- **Preprint**: an early version posted before peer review (medRxiv, bioRxiv). It can duplicate the later journal version.
- **Retraction**: a paper formally withdrawn, for example because of errors or misconduct. Citing retracted work is a quality signal worth flagging.
- **MeSH**: Medical Subject Headings, PubMed's controlled vocabulary of topics.
- **JATS XML**: the XML format of full-text papers in PubMed Central / Europe PMC. We parse it to find in-text mentions.
- **Canonical record**: the single "official" record after duplicates are merged.
- **Policy**: institution-specific settings that define what "internal" means and the matching thresholds.

---

## 3. Fuzzy matching and the RapidFuzz score

### 3.1 The problem
These two titles are the same paper, but an exact comparison says they differ:
- "Effect of Metformin on Type 2 Diabetes: A Randomized Trial"
- "Effects of metformin on type-2 diabetes. A randomised trial."

**Fuzzy matching** measures how similar two texts are. **RapidFuzz** is a fast Python library for it.

### 3.2 The score
A number from 0 to 100:
- 100 = identical (after normalization)
- about 90–95 = almost certainly the same, small typos or punctuation differences
- 80–90 = uncertain, a human should look
- below 80 = treat as different

```python
from rapidfuzz import fuzz

a = "effect of metformin on type 2 diabetes a randomized trial"
b = "effects of metformin on type 2 diabetes a randomised trial"
print(fuzz.ratio(a, b))             # character-level similarity
print(fuzz.token_sort_ratio(a, b))  # ignores word order
print(fuzz.token_set_ratio(a, b))   # handles extra or missing words (best for titles)
```

### 3.3 Why the score alone is not enough
"Study of Drug X, Part 1" and "Study of Drug X, Part 2" score very high but are different papers. So CiteWise:
1. Uses a high threshold (default 92) for auto-merging.
2. Also requires the year to be within 1 and at least one shared author surname.
3. Blocks merges when numbers, roman numerals, or "part/phase/trial" tokens differ.
4. Sends the 80–92 band to a human review queue.
5. Remembers rejected merges so they never come back.

Principle: **it is better to leave a duplicate unmerged and flagged than to wrongly merge two different papers.**

### 3.4 Blocking
Comparing every record with every other record is slow. We first group records by (first-author surname, year) and only compare inside a group. This keeps the pipeline fast.

---

## 4. Hashing and verification in plain words

- A **hash** (SHA-256) turns any text into a fixed-length fingerprint. Change one character and the fingerprint changes completely.
- For each citation we build an **evidence record** (both papers' identifiers, source links, context sentence, rule that decided the class, retrieval time) and hash it.
- A **Merkle root** combines all those fingerprints into one final fingerprint for the whole report.
- The report PDF prints the root hash and a **QR code** to `/verify/{report_id}`. The verify page recomputes the hashes from stored records and shows **MATCH** or **MISMATCH**. Users can also paste the report JSON to recompute the root in their browser.
- This is tamper-evidence, not blockchain. We do not need a blockchain.

What it proves: the report was not altered after generation, and every record points to its source. What it does not prove: that upstream databases are correct. That is why every record links to the original DOI.

---

## 5. Libraries and tools

### 5.1 Backend (Python 3.11+)
| Purpose | Library | Install |
|---|---|---|
| API framework | `fastapi`, `uvicorn` | `pip install fastapi "uvicorn[standard]"` |
| Settings / validation | `pydantic`, `pydantic-settings` | `pip install pydantic pydantic-settings` |
| Database | `sqlalchemy`, `psycopg[binary]` | `pip install sqlalchemy "psycopg[binary]"` |
| HTTP | `httpx`, `tenacity` | `pip install httpx tenacity` |
| Data processing | `pandas` | `pip install pandas` |
| Fuzzy matching | `rapidfuzz` | `pip install rapidfuzz` |
| Text cleanup | `unidecode`, `regex` | `pip install unidecode regex` |
| Full-text XML | `lxml` | `pip install lxml` |
| Sentence splitting | `pysbd` | `pip install pysbd` |
| Graph analysis | `networkx` | `pip install networkx` |
| QR codes | `qrcode[pil]` | `pip install "qrcode[pil]"` |
| PDF | `jinja2`, `weasyprint` (Linux/Docker), fallback `reportlab` | `pip install jinja2 weasyprint` |
| BibTeX | `bibtexparser` | `pip install bibtexparser` |
| Testing | `pytest`, `pytest-asyncio` | `pip install pytest pytest-asyncio` |
| Lint | `ruff` | `pip install ruff` |
| Optional LLM | `anthropic` | `pip install anthropic` |
| Built-in | `hashlib`, `json`, `unicodedata`, `re` | (standard library) |

Windows note: WeasyPrint needs extra system libraries and can be painful to install on Windows. Use Docker, or fall back to `reportlab`, or the frontend print-CSS page.

### 5.2 Frontend (TypeScript)
| Purpose | Library |
|---|---|
| Framework | `next` (App Router), `react`, `typescript` |
| Styling | `tailwindcss`, `shadcn/ui`, `lucide-react` |
| Data fetching | `@tanstack/react-query` |
| Tables | `@tanstack/react-table` |
| Charts | `recharts` |
| Network graph | `react-force-graph-2d` |
| QR code | `qrcode.react` |
| Animation | `framer-motion` |
| Forms | `react-hook-form`, `zod` |
| Theme | `next-themes` |

Install example:
```bash
npx create-next-app@latest frontend --typescript --tailwind --app
cd frontend
npx shadcn@latest init
npm i @tanstack/react-query @tanstack/react-table recharts react-force-graph-2d qrcode.react framer-motion react-hook-form zod next-themes lucide-react
```

### 5.3 Infrastructure
- PostgreSQL via Supabase or Neon (free tiers) or local Docker.
- Frontend on Vercel; backend on Render or Railway; or the whole stack locally with Docker Compose for the demo.
- Git and GitHub for the repo.

---

## 6. Data sources and datasets

Important: for this problem the real data comes from free APIs. Kaggle has little that fits (mostly non-medical or machine-learning benchmark graphs without author affiliations). Use the sources below.

### 6.1 Main sources (use these)
| Source | What it gives | Link |
|---|---|---|
| **OpenAlex** | Papers, citing papers, authors, institutions with ROR IDs, retraction flags. Our backbone | API `https://api.openalex.org`, docs `https://developers.openalex.org` |
| **PubMed / NCBI E-utilities** | Medical metadata, PMIDs, MeSH, publication types | `https://pubmed.ncbi.nlm.nih.gov`, E-utilities docs at `https://www.ncbi.nlm.nih.gov/books/NBK25501/` |
| **Europe PMC REST API** | Search and free full-text XML for open-access papers (for in-text mentions) | `https://europepmc.org/RestfulWebService` |
| **Crossref REST API** | DOI metadata, publisher data, update/retraction information | `https://api.crossref.org` |
| **ROR** | Institution registry and affiliation matching API | `https://ror.org`, API base `https://api.ror.org/v2/organizations` |
| **NIH iCite** | PubMed-to-PubMed citation data (NIH Open Citation Collection) | `https://icite.od.nih.gov` |
| **OpenCitations** | Open citation links between DOIs | `https://opencitations.net` |

**OpenAlex needs a free API key now.** The old "polite pool" (adding `mailto=` to requests) was replaced in February 2026, and usage is metered on a daily budget. Create a free key from the OpenAlex site (see `https://developers.openalex.org/guides/authentication` for the current method), put it in `OPENALEX_API_KEY`, cache every response, and fetch your demo data **before** the hackathon so you never depend on live calls during the demo.

### 6.2 Ready-made downloads (optional, for testing or backup)
| Dataset | What it is | Link |
|---|---|---|
| PubMed Diabetes citation graph | 19,717 PubMed papers on diabetes with a citation graph (44,338 links); no affiliations, good for testing graph logic | `https://linqs.soe.ucsc.edu/data` (also available via the DGL library) |
| Parsed OpenCitations + PubMed data (Univ. of Illinois) | Huge OpenCitations edge list (about 121M nodes, 1.96B edges) plus 2024 PubMed metadata table with PMIDs and DOIs; only for a big-data angle | `https://experts.illinois.edu/en/datasets/parsed-open-citations-and-pubmed-data/` |
| Curated list of scholarly datasets | Index of citation, PubMed, and affiliation datasets (self-citation analysis on PMC, MapAffil, iCite, etc.) | `https://github.com/shauryr/awesome-scholarly-data-analysis` |
| arXiv on Kaggle | Large arXiv metadata set; not medical, only for practicing | `https://www.kaggle.com/datasets/Cornell-University/arxiv` |

### 6.3 Example API calls
```bash
# Works by an author (replace the ID and add your API key per the OpenAlex docs)
curl "https://api.openalex.org/works?filter=authorships.author.id:A5023888391&per-page=50"

# Papers that cite a given work (the citing works, with authors and institutions)
curl "https://api.openalex.org/works?filter=cites:W2741809807&per-page=200&select=id,doi,title,publication_year,authorships,ids,is_retracted"

# Find an institution and read its ROR ID
curl "https://api.openalex.org/institutions?search=All%20India%20Institute%20of%20Medical%20Sciences"

# Europe PMC: full text XML of an open-access paper
curl "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7523456/fullTextXML"

# ROR: match a messy affiliation string
curl "https://api.ror.org/v2/organizations?affiliation=Dept%20of%20Cardiology%2C%20AIIMS%20Delhi%2C%20India"

# Crossref: metadata for a DOI
curl "https://api.crossref.org/works/10.1038/s41586-020-2649-2"
```
Notes: OpenAlex paginates with `per-page` (max 200) and `cursor=*`. Field names such as `authorships[].institutions[].ror` and `ids.pmid` are in OpenAlex's Work object (check the docs if a field name has changed). `select=` limits the response to the fields you need and saves your daily budget.

---

## 7. How we build the demo dataset

1. **Pick the institution and 5 researchers.** Choose a real medical institution with many OpenAlex-indexed papers. Find its OpenAlex institution ID and ROR ID with the institutions endpoint, then pick 5 productive authors.
2. **Fetch.** Run `backend/scripts/fetch_demo_data.py`: author works, then citing works per work. Cache every response to `backend/data/cache/` and commit the cache.
3. **Plant noise** with `backend/scripts/make_messy_data.py` (seed 42):
   - Duplicate records (remove DOI, typos, spelling variants, dash vs colon, preprint versions).
   - Repeated mention rows (2–7 extra rows for about 30% of pairs; use real Europe PMC mentions where possible).
   - "Part 1 / Part 2" look-alike title traps to prove the guard.
   - Optional synthetic citation ring and a citation to a real retracted work (OpenAlex filter `is_retracted:true`).
4. **Ground truth.** The script writes `ground_truth.json` (expected merges, expected unique citation counts, expected classes). Tests compare pipeline output against it.
5. **Disclose.** Every planted row has `is_synthetic = true`. The UI shows a banner and the PDF footer states it. Pitch wording: "real OpenAlex data plus deliberately planted errors, so you can watch the cleaning work."

Never present planted data as real results.

---

## 8. How CiteWise is different (positioning)

Most teams will build a dashboard that shows corrected citation counts. CiteWise differs on four main points plus extras:

1. **Explainability**: every number is clickable and shows which citations were kept, merged, or reclassified, and which rule decided it.
2. **Verifiability**: evidence records are hashed; reports carry a root hash and a QR code to a public verify page, so a committee can check without trusting us.
3. **The raw-vs-verified waterfall**: shows exactly where inflation comes from, step by step.
4. **Configurable institutional policy**: each university defines "internal" differently; admins choose the rule and see numbers recompute live.
5. Extras: human review queue (no silent wrong merges), integrity flags (retracted citations, citation rings, abnormal internal ratio), promotion-ready PDF, medical-aware metadata (PMID/PMCID, MeSH, publication types).

**Versus Google Scholar, Scopus, Web of Science:** those are excellent databases and we use similar open data (OpenAlex, PubMed). Some of them can exclude an author's self-citations, but as far as we know they do not offer an institution-level audit trail where every citation is classified as self, internal, or external with a visible reason, nor a tamper-evident report a college can hand to a promotion committee. CiteWise is the verification layer on top. (Be careful to say "as far as we know" and never claim to have compared their numbers unless you actually did.)

---

## 9. Pitch

### 9.1 30-second pitch (memorize)
"Promotion committees rely on citation counts they can't verify. Counts get inflated by duplicate records, by one paper mentioning another many times, and by citations from the researcher's own college. CiteWise cleans the data using fair counting rules, separates self, internal, and external citations, and produces reports where every number can be clicked, traced to its source, and verified with a hash and QR code. We don't just give a number, we give proof."

### 9.2 5-minute story
1. Problem (30s) → 2. Load data and show the pipeline (45s) → 3. Waterfall on a researcher (60s) → 4. Seven mentions counted once (45s) → 5. Policy change recomputes live (45s) → 6. Evidence card (45s) → 7. PDF, QR scan, verify page MATCH, tamper test MISMATCH (45s) → 8. Limitations, next steps, closing line (15s).

Closing line: "AI assists, rules decide, everything is auditable."

---

## 10. Jury Q&A with model answers

**How to answer:** direct answer, one reason, one example. Say "we deliberately chose...". Admit limits openly. End by linking back to explainability and verifiability.

### A. Differentiation
**Q1. Many teams solve this problem. What is special about yours?**
"Most solutions stop at a dashboard of corrected counts. We differ in four ways: explainability (every number drills down to citations and the deciding rule), verifiability (SHA-256 evidence hashes, a Merkle root, QR code and a public verify page), the raw-vs-verified waterfall that shows where inflation comes from, and a configurable institutional policy so each university defines 'internal' its own way."

**Q2. How is this different from Google Scholar, Scopus, or Web of Science?**
"They are excellent databases, and we use similar open data. Some can exclude an author's self-citations, but as far as we know they don't give an institution-level audit trail with self, internal, and external classes and visible reasons, or a tamper-evident report for a promotion committee. We are the verification layer on top, not a replacement."

### B. Problem understanding
**Q3. Why does this matter?**
"Promotions, grants, and rankings depend on citation numbers. If the numbers are inflated or unverifiable, honest researchers lose and institutions can't defend decisions. In medicine it matters more, because research influences clinical practice."

**Q4. Why count repeated mentions as one citation?**
"A citation measures how many independent works relied on a paper, not how many sentences mention it. If paper B mentions A seven times, B recognized A once. Counting seven lets one article inflate a score. We still store all seven mentions and show them, because mention frequency can show how central the paper is. It just doesn't change the citation count."

**Q5. Why separate internal and external citations?**
"External citations show independent recognition. Internal ones are legitimate but easier to coordinate. We don't delete them; we separate them so the committee sees both numbers and decides."

### C. Technical
**Q6. How do you detect duplicates?**
"A cascade, cheapest and most certain first: exact normalized DOI, PMID, or PMCID; then a hash of normalized title, year, and first author; then fuzzy title matching with RapidFuzz at 92 or above plus year within one and a shared author; uncertain cases between 80 and 92 go to a review queue. Every merge is logged with reason and confidence."

**Q7. What is the RapidFuzz score and why trust it?**
"A similarity score from 0 to 100. We don't trust it alone because 'Part 1' and 'Part 2' of a study score high. We combine it with year and author checks, block merges when numbers or part tokens differ, and keep a review queue. We prefer an unmerged flagged duplicate over a wrong merge."

**Q8. How do you decide two authors are from the same institution?**
"We map every affiliation to a ROR ID, the registry's unique institution ID, so 'AIIMS Delhi' and 'All India Institute of Medical Sciences' resolve to the same ID. Then it's an ID comparison. Admins configure the rule, for example any author vs first and last author only."

**Q9. What if an author changed institutions?**
"We use the affiliation listed on the paper at publication time, not the author's current one, so classification stays historically fair."

**Q10. How do you count mentions inside a paper?**
"For open-access papers we parse the full-text XML from Europe PMC, find each in-text reference marker, and record its sentence and section. For papers without free full text, the reference list lists each cited work once, and our database constraint on the (citing, cited) pair guarantees a single edge."

**Q11. Where does AI come in? Isn't AI unreliable for something this serious?**
"We deliberately keep the core deterministic: rules decide the counts, so results are reproducible and explainable. AI is optional and only suggests answers for borderline review items, and a human approves them. AI assists, rules decide, everything is auditable."

**Q12. Is the verification blockchain?**
"No, and we don't need it. Each evidence record is hashed with SHA-256, the hashes roll up into a Merkle root stored on the report and printed on the PDF with a QR code. If anyone changes a single record, the recomputed root no longer matches."

### D. Data and accuracy
**Q13. Where does your data come from and is it reliable?**
"OpenAlex for papers, citations, authors, and institutions; PubMed and Europe PMC for medical metadata and full text; Crossref for DOI details; ROR for institutions. These are open, widely used sources. Every record stores its source and retrieval time."

**Q14. What about papers your sources miss?**
"No database is complete. Reports show data coverage, and we support CSV and BibTeX upload so institutions can add records. We prefer transparent coverage over a falsely precise number."

**Q15. How accurate is your deduplication? Did you measure it?**
Only quote numbers you measured. "We validated against a ground-truth file of planted duplicates: [insert your real result]. Because thresholds are conservative and uncertain cases go to review, our priority is avoiding false merges. A larger labeled evaluation is the next step." If unmeasured, say that honestly.

**Q16. Is the demo data real?**
"The base data is real OpenAlex data for [institution], cached for reliability. We added deliberately planted errors, flagged in the database and in the UI, to demonstrate the cleaning. The same pipeline runs on any researcher."

### E. Ethics and limitations
**Q17. Could this be unfair to some researchers?**
"Citation counts already carry biases like field size and language. We don't claim to remove them; we reduce one problem, inflation, and recommend the numbers as evidence for human committees, not automatic decisions. Field-normalized scoring with MeSH topics is a planned improvement."

**Q18. Does separating internal citations hurt collaborative departments?**
"We don't penalize them, we separate them. A collaborating department naturally has internal citations, and the report shows that context. The committee decides the weight, and the policy engine lets the institution configure it."

**Q19. Privacy?**
"We use public bibliographic data only. No patient data or private records."

**Q20. What are your limitations?**
"Three: coverage depends on open databases; author-name disambiguation is never perfect, so we keep a review queue; full-text mention counting works only for open-access papers. We flag uncertainty instead of hiding it."

### F. Practical and business
**Q21. Who would use this?** Medical colleges, promotion committees, accreditation and ranking bodies, and researchers who want a verified record.

**Q22. Can it scale?** "Yes. Logic is database-driven with unique constraints, so more researchers just means more rows. We batch ingestion and cache API responses; the slowest step is fetching, which can run in the background."

**Q23. How would it be sustained?** "Institutional subscriptions for ongoing reports and policy setup, with a free tier for individual researchers to check their own verified record."

**Q24. What next?** "Retraction alerts at scale, field-normalized scoring, bigger citation-ring detection, ORCID login so researchers can claim and correct profiles, and integration with institutional HR systems."

### G. Curveballs
**Q25. What if someone fakes the input data?** "Verification proves a report wasn't changed after generation and shows each record's origin. It doesn't prove the upstream source is truthful, which is why every record links to the original DOI for checking."

**Q26. Why believe your counts over Google Scholar's?** "You don't have to. Every number comes with a drill-down showing the exact records and rules, and you can verify the report yourself."

---

## 11. Honest limitations (state proactively)

1. Coverage is limited to open databases (OpenAlex, PubMed, Europe PMC, Crossref).
2. Author-name disambiguation is imperfect; ambiguous matches go to review.
3. In-text mention counting needs free full text; otherwise we rely on reference lists.
4. Hashes prove integrity after generation, not the truth of upstream data.
5. Demo includes synthetic noise for demonstration, disclosed in the UI.
6. Citation metrics have known biases (field size, language); CiteWise supports human judgment and does not replace it.

---

## 12. Day-before checklist and roles

### 12.1 Do tonight / before the hackathon
- [ ] Get a free OpenAlex API key and test one call.
- [ ] Choose the institution and 5 researchers; run `fetch_demo_data.py` and commit the cache.
- [ ] Generate the messy dataset and `ground_truth.json`.
- [ ] Set up the repo, Docker Compose, Supabase/Neon DB, and Vercel/Render accounts.
- [ ] Agree on the JSON response shapes (PRD Section 12) so frontend and backend can work in parallel.
- [ ] Test WeasyPrint install; if it fails, plan the reportlab or print-CSS fallback.
- [ ] Prepare 2 slides only (problem, solution) so most time goes to the live demo.

### 12.2 Roles (3–4 people)
| Role | Responsibilities |
|---|---|
| A. Data and pipeline | Fetch scripts, cache, messy data, ingest, normalize, dedup, edges, mentions |
| B. Rules and reports | Classification, policy engine, metrics, integrity flags, evidence hashing, verify endpoint, PDF |
| C. Frontend | Pages, waterfall chart, drawer, review UI, verify page |
| D. Pitch and QA | Demo script, README, tests, jury Q&A rehearsal, screenshots, backup video of the demo |

With three people, merge A and B.

### 12.3 Demo safety
- Record a backup video of the full demo.
- Run in `OFFLINE_MODE=true`.
- Have the seeded database dump ready for a fast restore.
- Open the verify page and PDF in tabs beforehand.

---

## 13. Quick command cheat sheet

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env
python scripts/fetch_demo_data.py          # needs network + OPENALEX_API_KEY; run once
python scripts/make_messy_data.py          # plants noise, writes ground_truth.json
python scripts/seed_db.py                  # loads data and runs the whole pipeline
uvicorn app.main:app --reload --port 8000
pytest -q

# Frontend
cd frontend
npm install
npm run dev                                # http://localhost:3000

# Docker (everything)
docker compose up --build
```

API docs (auto-generated by FastAPI): `http://localhost:8000/docs`.
