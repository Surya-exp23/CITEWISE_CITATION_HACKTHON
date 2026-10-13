#!/usr/bin/env python3
"""
fetch_demo_data.py — TASK 1 of the CiteWise demo dataset build.

Fetches REAL data from the OpenAlex API:
  1. Institution: All India Institute of Medical Sciences (New Delhi), ROR https://ror.org/02dwcqs71
  2. 5 real researchers (by works_count at that institution, all with ORCIDs)
  3. Up to 25 works per researcher (sorted by cited_by_count desc)
  4. Citing works for the ~20 most-cited works (up to 25 citing works each)

Caches EVERY raw API response as data/cache/<sha1-of-full-url>.json.
Builds the clean intermediate schema in data/demo/clean/*.json
(all is_synthetic=false). Noise planting happens later in make_messy_data.py.

Run:  python3 scripts/fetch_demo_data.py
"""
import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import urlencode

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data", "cache")
CLEAN_DIR = os.path.join(ROOT, "data", "demo", "clean")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(CLEAN_DIR, exist_ok=True)

BASE = "https://api.openalex.org"
MAILTO = "citewise-demo@example.com"
SLEEP = 0.3
TIMEOUT = 30

MAIN_ROR = "https://ror.org/02dwcqs71"

# 5 real AIIMS researchers (openalex id, display name, orcid) — chosen 2026-10-13
# from /authors?filter=last_known_institutions.ror:<ROR>&sort=works_count:desc
RESEARCHERS = [
    ("https://openalex.org/A5018621533", "Nikhil Tandon", "https://orcid.org/0000-0003-4604-1986"),   # endocrinology
    ("https://openalex.org/A5000530935", "Sameer Bakhshi", "https://orcid.org/0000-0001-9367-4407"),   # oncology
    ("https://openalex.org/A5015474583", "Manjari Tripathi", "https://orcid.org/0000-0003-2201-5644"), # neurology
    ("https://openalex.org/A5039572099", "Rakesh Lodha", "https://orcid.org/0000-0003-2608-1163"),     # pediatrics
    ("https://openalex.org/A5066444862", "Peush Sahni", "https://orcid.org/0000-0002-6910-062X"),       # surgery
]

WORKS_PER_RESEARCHER = 25
TOP_CITED_FOR_CITERS = 20
CITERS_PER_WORK = 25

SELECT_WORKS = ("id,doi,title,publication_year,authorships,ids,type,is_retracted,"
                "primary_location,cited_by_count")


def cache_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


@retry(stop=stop_after_attempt(4),
       wait=wait_exponential(multiplier=2, min=2, max=30),
       retry=retry_if_exception_type((requests.RequestException,)),
       reraise=True)
def _get(url: str) -> dict:
    r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "CiteWiseDemo/1.0"})
    r.raise_for_status()
    return r.json()


def fetch(path: str, params: dict) -> dict:
    """GET with disk cache (sha1 of full URL), 0.3s sleep between live calls."""
    params = dict(params)
    params["mailto"] = MAILTO
    url = f"{BASE}{path}?{urlencode(params)}"
    key = cache_key(url)
    cpath = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.exists(cpath):
        with open(cpath, encoding="utf-8") as f:
            return json.load(f)
    time.sleep(SLEEP)
    data = _get(url)
    with open(cpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def norm_doi(doi):
    if not doi:
        return None
    d = doi.strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/",
              "https://dx.doi.org/", "doi:"):
        if d.startswith(p):
            d = d[len(p):]
    return d.strip().rstrip(".,;") or None


def extract_id(ids: dict, kind: str):
    """ids like {'pmid': 'https://pubmed.ncbi.nlm.nih.gov/12345/', 'pmcid': 'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6789/'}"""
    v = (ids or {}).get(kind)
    if not v:
        return None
    m = re.search(r"(PMC)?(\d+)", str(v).upper())
    if not m:
        return None
    return ("PMC" + m.group(2)) if kind == "pmcid" else m.group(2)


def clean_name(s):
    return re.sub(r"\s+", " ", (s or "").strip()) or None


def main():
    print("== CiteWise demo data fetch (OpenAlex) ==")
    works_by_oa = {}          # openalex_id -> raw work dict
    researcher_work_oa = {}   # researcher oa id -> [work oa ids]

    # --- 1. researcher works ---
    for oa_id, name, orcid in RESEARCHERS:
        print(f"fetching works for {name} ...")
        data = fetch("/works", {
            "filter": f"author.id:{oa_id}",
            "sort": "cited_by_count:desc",
            "per-page": WORKS_PER_RESEARCHER,
            "select": SELECT_WORKS,
        })
        got = []
        for w in data.get("results", []):
            if not w.get("id") or not w.get("title"):
                continue
            works_by_oa[w["id"]] = w
            got.append(w["id"])
        researcher_work_oa[oa_id] = got
        print(f"  -> {len(got)} works")

    # --- 2. citing works for top-cited works ---
    ranked = sorted(works_by_oa.values(),
                    key=lambda w: -(w.get("cited_by_count") or 0))
    targets = [w for w in ranked if (w.get("cited_by_count") or 0) > 0][:TOP_CITED_FOR_CITERS]
    print(f"fetching citing works for top {len(targets)} cited works ...")
    edges = set()  # (citing_oa, cited_oa)
    for w in targets:
        short = w["id"].split("/")[-1]
        print(f"  cites:{short} ({w.get('cited_by_count')} cited_by) ...")
        data = fetch("/works", {
            "filter": f"cites:{w['id']}",
            "per-page": CITERS_PER_WORK,
            "select": SELECT_WORKS,
        })
        n = 0
        for c in data.get("results", []):
            if not c.get("id") or not c.get("title") or c["id"] == w["id"]:
                continue
            works_by_oa.setdefault(c["id"], c)
            edges.add((c["id"], w["id"]))
            n += 1
        print(f"    -> {n} citing works")

    # --- 2b. per-researcher citing fetch: guarantee every researcher has edges ---
    # (the global top-20 above is dominated by a few blockbuster papers)
    target_ids = {w["id"] for w in targets}
    for oa_id, name, orcid in RESEARCHERS:
        cands = sorted(
            (works_by_oa[x] for x in researcher_work_oa[oa_id]),
            key=lambda w: -((w.get("cited_by_count") or 0)))
        cands = [w for w in cands if (w.get("cited_by_count") or 0) > 0 and w["id"] not in target_ids][:5]
        print(f"  per-researcher citing fetch for {name}: {len(cands)} works")
        for w in cands:
            short = w["id"].split("/")[-1]
            data = fetch("/works", {
                "filter": f"cites:{w['id']}",
                "per-page": 10,
                "select": SELECT_WORKS,
            })
            n = 0
            for c in data.get("results", []):
                if not c.get("id") or not c.get("title") or c["id"] == w["id"]:
                    continue
                works_by_oa.setdefault(c["id"], c)
                edges.add((c["id"], w["id"]))
                n += 1
            target_ids.add(w["id"])
            print(f"    cites:{short} -> {n} citing works")

    print(f"TOTAL works: {len(works_by_oa)}, TOTAL edges: {len(edges)}")
    retracted = [w["id"] for w in works_by_oa.values() if w.get("is_retracted")]
    preprints = [w["id"] for w in works_by_oa.values() if (w.get("type") or "") == "preprint"]
    print(f"retracted works found: {len(retracted)}, preprints found: {len(preprints)}")

    # --- 3. build clean schema (deterministic ordering) ---
    oa_sorted = sorted(works_by_oa.keys())
    wid = {oa: f"W{i+1}" for i, oa in enumerate(oa_sorted)}

    author_key = {}   # openalex author id -> A#
    authors = []      # list of dicts

    def get_author(aid, display_name, orcid):
        if aid not in author_key:
            key = f"A{len(author_key)+1}"
            author_key[aid] = key
            authors.append({"author_key": key, "openalex_id": aid,
                            "orcid": orcid, "display_name": clean_name(display_name) or aid})
        return author_key[aid]

    # researchers get A1..A5 first (stable, meaningful keys)
    researcher_keys = {}
    for oa_id, name, orcid in RESEARCHERS:
        k = get_author(oa_id, name, orcid)
        researcher_keys[k] = oa_id

    institutions = {}   # ror -> dict
    authorships = []
    works_out = []

    for oa in oa_sorted:
        w = works_by_oa[oa]
        ids = w.get("ids") or {}
        pl = (w.get("primary_location") or {})
        src = (pl.get("source") or {})
        works_out.append({
            "record_id": wid[oa],
            "openalex_id": oa,
            "doi": norm_doi(w.get("doi")),
            "pmid": extract_id(ids, "pmid"),
            "pmcid": extract_id(ids, "pmcid"),
            "title": clean_name(w.get("title")),
            "year": w.get("publication_year"),
            "venue": clean_name(src.get("display_name")),
            "pub_type": w.get("type"),
            "is_preprint": (w.get("type") or "") == "preprint",
            "is_retracted": bool(w.get("is_retracted")),
            "source": "openalex",
            "is_synthetic": False,
        })
        for ash in (w.get("authorships") or []):
            a = ash.get("author") or {}
            aid = a.get("id")
            if not aid:
                continue
            key = get_author(aid, a.get("display_name"), a.get("orcid"))
            insts = ash.get("institutions") or []
            ror = None
            raw_aff = None
            if insts:
                ror = insts[0].get("ror")
                raw_aff = clean_name(insts[0].get("display_name"))
                for inst in insts:
                    rr = inst.get("ror")
                    if rr and rr not in institutions:
                        institutions[rr] = {
                            "ror_id": rr,
                            "openalex_id": inst.get("id"),
                            "name": clean_name(inst.get("display_name")) or rr,
                            "country_code": inst.get("country_code"),
                        }
            authorships.append({
                "work_record_id": wid[oa],
                "author_key": key,
                "institution_ror": ror,
                "position": ash.get("author_position") or "middle",
                "raw_affiliation": raw_aff,
            })

    # ensure the main institution exists even if never listed first
    if MAIN_ROR not in institutions:
        institutions[MAIN_ROR] = {
            "ror_id": MAIN_ROR,
            "openalex_id": "https://openalex.org/I63739035",
            "name": "All India Institute of Medical Sciences",
            "country_code": "IN",
        }

    rows_out = []
    for citing_oa, cited_oa in sorted(edges):
        rows_out.append({
            "raw_citing_record_id": wid[citing_oa],
            "raw_cited_record_id": wid[cited_oa],
            "row_kind": "reference_entry",
            "context_sentence": None,
            "section": None,
            "source": "openalex",
            "is_synthetic": False,
        })

    meta = {
        "institution": {"ror_id": MAIN_ROR,
                        "openalex_id": "https://openalex.org/I63739035",
                        "name": "All India Institute of Medical Sciences",
                        "country_code": "IN"},
        "researchers": [{"author_key": get_author(oa, n, o), "openalex_id": oa,
                         "display_name": n, "orcid": o} for oa, n, o in RESEARCHERS],
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stats": {"works": len(works_out), "authors": len(authors),
                  "institutions": len(institutions), "authorships": len(authorships),
                  "raw_rows": len(rows_out),
                  "retracted_works": len(retracted), "preprints": len(preprints)},
    }

    def dump(name, obj):
        with open(os.path.join(CLEAN_DIR, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)

    dump("works.json", works_out)
    dump("authors.json", authors)
    dump("institutions.json", list(institutions.values()))
    dump("authorships.json", authorships)
    dump("raw_citation_rows.json", rows_out)
    dump("meta.json", meta)

    print("clean data written to", CLEAN_DIR)
    print(json.dumps(meta["stats"], indent=1))


if __name__ == "__main__":
    sys.exit(main())
