#!/usr/bin/env python3
"""
make_messy_data.py — plants deterministic synthetic noise (seed=42) into the
clean OpenAlex dataset so the CiteWise pipeline has something to clean.

Reads : data/demo/clean/*.json   (all real, is_synthetic=false)
Writes: data/demo/works.json, authors.json, institutions.json,
        authorships.json, raw_citation_rows.json, ground_truth.json

Every planted row carries is_synthetic=true.

Planted noise
  1. Duplicate work records (~20% of works, 1-2 aliases each): stripped DOI,
     title typo, colon->dash, British/American spelling flip, dropped subtitle
     word, or a medRxiv preprint version. ~30% of aliases also get 1-2
     duplicated citation rows (drives duplicates_removed in the waterfall).
  2. Repeated mentions: ~30% of citation pairs get 2-7 extra mention rows
     with invented context sentences (synthetic).
  3. Look-alike traps: 3 synthetic pairs differing ONLY by "Part 1"/"Part 2"
     (or "Trial 1"/"Trial 2") with overlapping authors -> must NOT auto-merge.
  4. Retraction: 1 synthetic retracted work + 1 synthetic citation to it
     (no real retracted work was found in the fetched data).
  5. Citation ring: 4 synthetic authors x 4 works, every ordered pair of
     authors exchanges 4 citations (48 rows).
  6. Preprint->published pair: medRxiv preprint (year-1) + journal article,
     near-identical title, same authors -> should merge as preprint_to_published.
  7. Coverage patch: verifies self/internal/external classes all exist for the
     researchers; synthesizes minimal patches if a class is missing.

Run: python3 scripts/make_messy_data.py
"""
import copy
import json
import os
import random
import re

random.seed(42)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_DIR = os.path.join(ROOT, "data", "demo", "clean")
DEMO_DIR = os.path.join(ROOT, "data", "demo")

MAIN_ROR = "https://ror.org/02dwcqs71"
RESEARCHER_KEYS = ["A1", "A2", "A3", "A4", "A5"]


def load(name):
    with open(os.path.join(CLEAN_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def dump(name, obj):
    with open(os.path.join(DEMO_DIR, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- typos etc.
US_UK = {
    "randomized": "randomised", "tumor": "tumour", "hemoglobin": "haemoglobin",
    "esophageal": "oesophageal", "anemia": "anaemia", "edema": "oedema",
    "pediatric": "paediatric", "behavior": "behaviour", "organized": "organised",
    "utilize": "utilise", "center": "centre", "diarrhea": "diarrhoea",
    "estrogen": "oestrogen", "leukemia": "leukaemia", "fiber": "fibre",
    "glycemic": "glycaemic", "program": "programme", "aging": "ageing",
    "ischemic": "ischaemic",
}


def typo_title(title):
    words = title.split()
    cands = [i for i, w in enumerate(words) if len(re.sub(r"\W", "", w)) >= 6]
    if not cands:
        return title
    i = random.choice(cands)
    w = words[i]
    letters = [j for j, ch in enumerate(w) if ch.isalpha()]
    if len(letters) < 2:
        return title
    j = random.choice(letters[:-1])
    lst = list(w)
    lst[j], lst[j + 1] = lst[j + 1], lst[j]
    words[i] = "".join(lst)
    return " ".join(words)


def spelling_flip(title):
    def rep(m):
        w = m.group(0)
        new = US_UK[w.lower()]
        return new.capitalize() if w[0].isupper() else new
    pat = re.compile(r"\b(" + "|".join(US_UK) + r")\b", re.IGNORECASE)
    out, n = pat.subn(rep, title, count=1)
    return out if n else None


def colon_to_dash(title):
    return title.replace(":", " -", 1) if ":" in title else None


def drop_subtitle_word(title):
    if ":" not in title:
        return None
    head, sub = title.split(":", 1)
    words = sub.split()
    if len(words) < 4:
        return None
    drop = random.randrange(len(words))
    words.pop(drop)
    return head + ": " + " ".join(words)


MENTION_SECTIONS = ["Introduction", "Methods", "Results", "Discussion"]
MENTION_TEMPLATES = [
    "Our findings are consistent with those reported by {fa} et al. [{n}], who demonstrated the effect in a comparable cohort.",
    "A similar association was previously described by {fa} and colleagues [{n}] in their {year} study.",
    "The prevalence estimates used here follow the methodology of {fa} et al. [{n}].",
    "As reviewed by {fa} et al. [{n}], the evidence on this intervention remains mixed.",
    "We adopted the diagnostic criteria proposed by {fa} and colleagues [{n}].",
    "These results extend the earlier observations of {fa} et al. [{n}], who reported comparable outcomes.",
    "Contrary to the conclusions of {fa} et al. [{n}], our data suggest a more modest effect size.",
    "The sample-size calculation was based on the effect sizes reported by {fa} et al. [{n}].",
]


def first_author_lastname(work_authors, authors_by_key):
    firsts = [a for a in work_authors if a["position"] == "first"]
    a = firsts[0] if firsts else (work_authors[0] if work_authors else None)
    if not a:
        return "the authors"
    name = (authors_by_key.get(a["author_key"]) or {}).get("display_name", "")
    return name.split()[-1] if name else "the authors"


# ---------------------------------------------------------------- main
def main():
    works = load("works.json")
    authors = load("authors.json")
    institutions = load("institutions.json")
    authorships = load("authorships.json")
    rows = load("raw_citation_rows.json")
    meta = load("meta.json")

    works_by_id = {w["record_id"]: w for w in works}
    authors_by_key = {a["author_key"]: a for a in authors}
    ash_by_work = {}
    for a in authorships:
        ash_by_work.setdefault(a["work_record_id"], []).append(a)

    expected_merges = []
    traps_not_merged = []
    new_works, new_authors, new_authorships, new_rows = [], [], [], []
    dup_counter = [0]
    syn_author_counter = [0]

    def next_dup_id():
        dup_counter[0] += 1
        return f"DUP{dup_counter[0]}"

    def next_syn_author(name):
        syn_author_counter[0] += 1
        key = f"SYN_A{syn_author_counter[0]}"
        new_authors.append({"author_key": key, "openalex_id": None,
                            "orcid": None, "display_name": name})
        authors_by_key[key] = new_authors[-1]
        return key

    def add_authorships(work_id, author_keys, ror=None, raw_aff=None):
        for i, ak in enumerate(author_keys):
            pos = "first" if i == 0 else ("last" if i == len(author_keys) - 1 else "middle")
            new_authorships.append({"work_record_id": work_id, "author_key": ak,
                                    "institution_ror": ror, "position": pos,
                                    "raw_affiliation": raw_aff})

    # ------------------------------------------------ 1. duplicate records
    cited_ids = {r["raw_cited_record_id"] for r in rows}
    # always duplicate the most-cited headline works so the waterfall shows it
    headline = sorted(cited_ids,
                      key=lambda wid: -sum(1 for r in rows if r["raw_cited_record_id"] == wid))[:25]
    pool = [w["record_id"] for w in works]
    n_dup = max(int(len(works) * 0.20), len(headline))
    dup_targets = list(dict.fromkeys(headline + random.sample(pool, n_dup)))[:n_dup]

    for wid in dup_targets:
        w = works_by_id[wid]
        n_alias = 2 if random.random() < 0.25 else 1
        for _ in range(n_alias):
            alias = copy.deepcopy(w)
            alias["record_id"] = next_dup_id()
            alias["openalex_id"] = None
            alias["is_synthetic"] = True
            alias["source"] = "csv_import"
            variant = random.choice(["strip_doi", "typo", "dash", "spelling", "dropword", "preprint"])
            title = w["title"] or ""
            if variant == "strip_doi":
                alias["doi"] = None
            elif variant == "typo":
                alias["title"] = typo_title(title)
                alias["doi"] = None
            elif variant == "dash":
                t = colon_to_dash(title)
                alias["title"] = t if t else typo_title(title)
                alias["doi"] = None
            elif variant == "spelling":
                t = spelling_flip(title)
                alias["title"] = t if t else typo_title(title)
                alias["doi"] = None
            elif variant == "dropword":
                t = drop_subtitle_word(title)
                alias["title"] = t if t else typo_title(title)
                alias["doi"] = None
            elif variant == "preprint":
                alias["title"] = title
                alias["venue"] = "medRxiv"
                alias["pub_type"] = "preprint"
                alias["is_preprint"] = True
                alias["source"] = "medRxiv"
                if isinstance(w.get("year"), int):
                    alias["year"] = w["year"] - 1
                alias["doi"] = "10.1101/2025.%02d.%02d.243%05d" % (
                    random.randint(1, 12), random.randint(1, 28), random.randint(0, 99999))
                alias["pmid"] = None
                alias["pmcid"] = None
            new_works.append(alias)
            # same authors (needed for fuzzy/author-overlap rules)
            for a in ash_by_work.get(wid, []):
                new_authorships.append({**a, "work_record_id": alias["record_id"]})
            reason = ("exact_id" if alias.get("doi") and alias["doi"] == w.get("doi")
                      else "preprint_to_published" if variant == "preprint"
                      else "title_year_author_hash"
                      if alias["title"] == w["title"] and alias.get("year") == w.get("year")
                      else "fuzzy_title")
            expected_merges.append({"record_ids": [wid, alias["record_id"]], "reason": reason})
            # ~30%: duplicate 1-2 citation rows through the alias record
            if random.random() < 0.30:
                rel = [r for r in rows
                       if r["raw_cited_record_id"] == wid or r["raw_citing_record_id"] == wid]
                for r in random.sample(rel, min(2, len(rel))) if rel else []:
                    nr = copy.deepcopy(r)
                    if nr["raw_cited_record_id"] == wid:
                        nr["raw_cited_record_id"] = alias["record_id"]
                    if nr["raw_citing_record_id"] == wid:
                        nr["raw_citing_record_id"] = alias["record_id"]
                    nr["is_synthetic"] = True
                    nr["source"] = "csv_import"
                    new_rows.append(nr)

    # ------------------------------------------------ 2. repeated mentions
    pairs = sorted({(r["raw_citing_record_id"], r["raw_cited_record_id"]) for r in rows})
    n_mention_pairs = int(len(pairs) * 0.30)
    for citing_id, cited_id in random.sample(pairs, n_mention_pairs):
        w = works_by_id[cited_id]
        fa = first_author_lastname(ash_by_work.get(cited_id, []), authors_by_key)
        for _ in range(random.randint(2, 7)):
            new_rows.append({
                "raw_citing_record_id": citing_id,
                "raw_cited_record_id": cited_id,
                "row_kind": "mention",
                "context_sentence": random.choice(MENTION_TEMPLATES).format(
                    fa=fa, n=random.randint(1, 60), year=w.get("year") or 2020),
                "section": random.choice(MENTION_SECTIONS),
                "source": "synthetic_demo",
                "is_synthetic": True,
            })

    # ------------------------------------------------ 3. Part 1 / Part 2 traps
    trap_defs = [
        ("Effect of metformin on glycemic control in type 2 diabetes mellitus: Part 1",
         "Effect of metformin on glycemic control in type 2 diabetes mellitus: Part 2",
         "Ananya Deshmukh", "Rohan Iyer"),
        ("Vitamin D supplementation in critically ill children: Trial 1",
         "Vitamin D supplementation in critically ill children: Trial 2",
         "Kavya Nair", "Arjun Menon"),
        ("Laparoscopic versus open appendectomy in adults: Part 1",
         "Laparoscopic versus open appendectomy in adults: Part 2",
         "Vikram Rao", "Sneha Kulkarni"),
    ]
    trap_n = [0]

    def trap_work(title, year, auth_keys):
        trap_n[0] += 1
        wid = f"TRAP{trap_n[0]}"
        new_works.append({"record_id": wid, "openalex_id": None, "doi": None,
                          "pmid": None, "pmcid": None, "title": title, "year": year,
                          "venue": "Indian Journal of Medical Research", "pub_type": "article",
                          "is_preprint": False, "is_retracted": False,
                          "source": "csv_import", "is_synthetic": True})
        add_authorships(wid, auth_keys, MAIN_ROR, "All India Institute of Medical Sciences")
        return wid

    for t1, t2, au1, au2 in trap_defs:
        k1, k2 = next_syn_author(au1), next_syn_author(au2)
        year = random.randint(2019, 2023)
        a = trap_work(t1, year, [k1, k2])
        b = trap_work(t2, year, [k1, k2])
        traps_not_merged.append([a, b])
        new_rows.append({"raw_citing_record_id": b, "raw_cited_record_id": a,
                         "row_kind": "reference_entry", "context_sentence": None,
                         "section": None, "source": "synthetic_demo", "is_synthetic": True})

    # ------------------------------------------------ 4. retracted paper citation
    ret_cited = max(cited_ids,
                    key=lambda wid: sum(1 for r in rows if r["raw_cited_record_id"] == wid))
    src_work = works_by_id[ret_cited]
    ret = copy.deepcopy(src_work)
    ret["record_id"] = "RET1"
    ret["openalex_id"] = None
    ret["is_retracted"] = True
    ret["is_synthetic"] = True
    ret["source"] = "synthetic_demo"
    new_works.append(ret)
    for a in ash_by_work.get(ret_cited, []):
        new_authorships.append({**a, "work_record_id": "RET1"})
    rk = next_syn_author("Demo Reviewer")
    new_works.append({"record_id": "RETC1", "openalex_id": None, "doi": None, "pmid": None,
                      "pmcid": None, "title": "A review citing a retracted study on the same topic",
                      "year": 2024, "venue": "BMJ Open", "pub_type": "review",
                      "is_preprint": False, "is_retracted": False,
                      "source": "synthetic_demo", "is_synthetic": True})
    add_authorships("RETC1", [rk], "https://ror.org/04fa4r544",
                    "Demo External University")
    new_rows.append({"raw_citing_record_id": "RETC1", "raw_cited_record_id": "RET1",
                     "row_kind": "reference_entry", "context_sentence": None,
                     "section": None, "source": "synthetic_demo", "is_synthetic": True})

    # ------------------------------------------------ 5. citation ring (4 authors, mutual >=4)
    ring_keys = [next_syn_author(n) for n in
                 ["Ring Author One", "Ring Author Two", "Ring Author Three", "Ring Author Four"]]
    ring_works = []
    for i, ak in enumerate(ring_keys):
        for j in range(4):
            wid = f"RW{i * 4 + j + 1}"
            new_works.append({"record_id": wid, "openalex_id": None, "doi": None,
                              "pmid": None, "pmcid": None,
                              "title": f"Observational study on metabolic markers cohort {i + 1}-{j + 1}",
                              "year": 2022, "venue": "Cureus", "pub_type": "article",
                              "is_preprint": False, "is_retracted": False,
                              "source": "synthetic_demo", "is_synthetic": True})
            add_authorships(wid, [ak], None, "Demo Synthetic Institute")
            ring_works.append(wid)
    for i in range(4):
        for j in range(4):
            if i == j:
                continue
            for k in range(4):  # i's work k cites j's work k -> 4 citations per ordered pair
                new_rows.append({"raw_citing_record_id": ring_works[i * 4 + k],
                                 "raw_cited_record_id": ring_works[j * 4 + k],
                                 "row_kind": "reference_entry", "context_sentence": None,
                                 "section": None, "source": "synthetic_demo",
                                 "is_synthetic": True})

    # ------------------------------------------------ 6. preprint -> published pair
    pk = next_syn_author("Preprint Author")
    new_works.append({"record_id": "PUB1", "openalex_id": None,
                      "doi": "10.1016/j.demo.2024.01.001", "pmid": None, "pmcid": None,
                      "title": "Dapagliflozin and cardiovascular outcomes in South Asian adults with type 2 diabetes: a multicentre cohort study",
                      "year": 2024, "venue": "The Lancet Regional Health - Southeast Asia",
                      "pub_type": "article", "is_preprint": False, "is_retracted": False,
                      "source": "synthetic_demo", "is_synthetic": True})
    add_authorships("PUB1", [pk], MAIN_ROR, "All India Institute of Medical Sciences")
    new_works.append({"record_id": "PRE1", "openalex_id": None,
                      "doi": "10.1101/2023.06.15.24304321", "pmid": None, "pmcid": None,
                      "title": "Dapagliflozin and cardiovascular outcomes in South Asian adults with type 2 diabetes: a multicentre cohort study",
                      "year": 2023, "venue": "medRxiv", "pub_type": "preprint",
                      "is_preprint": True, "is_retracted": False,
                      "source": "medRxiv", "is_synthetic": True})
    add_authorships("PRE1", [pk], MAIN_ROR, "All India Institute of Medical Sciences")
    expected_merges.append({"record_ids": ["PUB1", "PRE1"], "reason": "preprint_to_published"})

    # ------------------------------------------------ assemble final tables
    works += new_works
    authors += new_authors
    authorships += new_authorships
    rows += new_rows
    # re-point the staging lists at the merged tables so later appends land correctly
    new_works, new_authors, new_authorships, new_rows = works, authors, authorships, rows
    works_by_id = {w["record_id"]: w for w in works}
    authors_by_key = {a["author_key"]: a for a in authors}
    ash_by_work = {}
    for a in authorships:
        ash_by_work.setdefault(a["work_record_id"], []).append(a)

    canonical = {}
    for w in works:
        canonical[w["record_id"]] = w["record_id"]
    for m in expected_merges:
        can, alias = m["record_ids"]
        canonical[alias] = can

    # ------------------------------------------------ 7. coverage: self/internal/external
    def work_authors(wid):
        return [a["author_key"] for a in ash_by_work.get(wid, [])]

    def work_rors(wid):
        return {a["institution_ror"] for a in ash_by_work.get(wid, [])
                if a["institution_ror"]}

    researcher_works = {rk: {w["record_id"] for w in works
                             if rk in work_authors(w["record_id"])}
                        for rk in RESEARCHER_KEYS}

    def classify_edge(citing_id, cited_id, rk):
        ca = work_authors(citing_id)
        if rk in ca:
            return "self"
        r_rors = set()
        for a in ash_by_work.get(cited_id, []):
            if a["author_key"] == rk and a["institution_ror"]:
                r_rors.add(a["institution_ror"])
        if work_rors(citing_id) & r_rors:
            return "internal"
        return "external"

    canon_edges = set()
    for r in rows:
        canon_edges.add((canonical[r["raw_citing_record_id"]],
                         canonical[r["raw_cited_record_id"]]))

    class_counts = {"self": 0, "internal": 0, "external": 0}
    per_researcher_edges = {rk: set() for rk in RESEARCHER_KEYS}
    for citing_id, cited_id in canon_edges:
        for rk in RESEARCHER_KEYS:
            if cited_id in researcher_works[rk]:
                per_researcher_edges[rk].add((citing_id, cited_id))
                class_counts[classify_edge(citing_id, cited_id, rk)] += 1
    print("classification coverage (researcher-scope edges):", class_counts)

    # patch any missing class with minimal synthetic rows (disclosed)
    patch_n = [0]

    def patch_cite(rk, kind):
        patch_n[0] += 1
        cited = sorted(researcher_works[rk])[0]
        cw = f"PX{patch_n[0]}"
        if kind == "self":
            aks, ror, aff = [rk, next_syn_author("Patch Coauthor")], MAIN_ROR, "All India Institute of Medical Sciences"
        elif kind == "internal":
            aks, ror, aff = [next_syn_author("Patch Internal Author")], MAIN_ROR, "All India Institute of Medical Sciences"
        else:
            aks, ror, aff = [next_syn_author("Patch External Author")], "https://ror.org/04fa4r544", "Demo External University"
        new_works.append({"record_id": cw, "openalex_id": None, "doi": None, "pmid": None,
                          "pmcid": None, "title": f"Follow-up analysis building on prior work ({kind} citation demo)",
                          "year": 2024, "venue": "PLOS ONE", "pub_type": "article",
                          "is_preprint": False, "is_retracted": False,
                          "source": "synthetic_demo", "is_synthetic": True})
        add_authorships(cw, aks, ror, aff)
        new_rows.append({"raw_citing_record_id": cw, "raw_cited_record_id": cited,
                         "row_kind": "reference_entry", "context_sentence": None,
                         "section": None, "source": "synthetic_demo", "is_synthetic": True})
        works_by_id[cw] = new_works[-1]
        ash_by_work[cw] = authorships[-(len(aks)):]
        canonical[cw] = cw
        return cw, cited

    for cls in ("self", "internal", "external"):
        if class_counts[cls] == 0:
            print(f"  !! no '{cls}' edges found -> adding synthetic patch")
            cw, cited = patch_cite(RESEARCHER_KEYS[0], cls)
            class_counts[cls] += 1
            per_researcher_edges[RESEARCHER_KEYS[0]].add((cw, cited))

    # refresh maps after patches
    authors_by_key = {a["author_key"]: a for a in authors}
    ash_by_work = {}
    for a in authorships:
        ash_by_work.setdefault(a["work_record_id"], []).append(a)

    # ------------------------------------------------ ground truth
    unique_cit = {rk: len(per_researcher_edges[rk]) for rk in RESEARCHER_KEYS}

    samples = []
    for rk in RESEARCHER_KEYS:
        by_class = {"self": [], "internal": [], "external": []}
        for citing_id, cited_id in sorted(per_researcher_edges[rk]):
            by_class[classify_edge(citing_id, cited_id, rk)].append((citing_id, cited_id))
        for cls in ("self", "internal", "external"):
            for citing_id, cited_id in by_class[cls][:8]:
                samples.append({"citing_record_id": citing_id, "cited_record_id": cited_id,
                                "researcher_key": rk, "expected": cls})

    stats = {
        "works": len(works),
        "authors": len(authors),
        "institutions": len(institutions),
        "authorships": len(authorships),
        "raw_rows": len(rows),
        "synthetic_rows": sum(1 for r in rows if r.get("is_synthetic")),
        "synthetic_works": sum(1 for w in works if w.get("is_synthetic")),
        "planted_duplicate_records": len([m for m in expected_merges
                                          if m["reason"] != "preprint_to_published"]),
        "mention_rows": sum(1 for r in rows if r["row_kind"] == "mention"),
        "traps": len(traps_not_merged),
        "ring_authors": len(ring_keys),
        "real_rows": sum(1 for r in rows if not r.get("is_synthetic")),
        "classification_coverage": class_counts,
    }

    ground_truth = {
        "expected_merges": expected_merges,
        "unique_citations_per_researcher": unique_cit,
        "sample_classifications": samples,
        "traps_not_merged": traps_not_merged,
        "ring_authors": ring_keys,
        "stats": stats,
    }

    dump("works.json", works)
    dump("authors.json", authors)
    dump("institutions.json", institutions)
    dump("authorships.json", authorships)
    dump("raw_citation_rows.json", rows)
    dump("ground_truth.json", ground_truth)

    print("demo data written to", DEMO_DIR)
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
