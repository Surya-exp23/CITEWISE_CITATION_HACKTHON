"""Demo dataset loader shared by scripts/seed_db.py and POST /ingest/demo.

Joins data/demo/works.json + authors.json + authorships.json into the
raw_works contract documented in services/dedup.py (nested authors with
institution_ror), and reads raw_citation_rows.json as raw_rows.
"""
import json
import os
from pathlib import Path

_ENV_DATA_DIR = os.environ.get("CITEWISE_DATA_DIR", "").strip()
DATA_DIR = Path(_ENV_DATA_DIR) if _ENV_DATA_DIR else Path(__file__).resolve().parent.parent.parent / "data" / "demo"

# Demo institution: real ROR of All India Institute of Medical Sciences.
AIIMS_ROR = "https://ror.org/02dwcqs71"
ROR_ALIASES = {
    "all india institute of medical sciences": AIIMS_ROR,
    "aiims": AIIMS_ROR,
}


def _split_name(display_name: str) -> tuple[str, str]:
    parts = (display_name or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]  # first, last


def load_demo_dataset(data_dir: Path | None = None):
    """Return (raw_works, raw_rows, ror_aliases)."""
    data_dir = Path(data_dir) if data_dir else DATA_DIR

    def load(name: str):
        with open(data_dir / f"{name}.json", encoding="utf-8") as f:
            return json.load(f)

    works = load("works")
    authors = {a["author_key"]: a for a in load("authors")}
    authorships_by_work: dict[str, list] = {}
    for ah in load("authorships"):
        authorships_by_work.setdefault(ah["work_record_id"], []).append(ah)
    institutions = {i["ror_id"]: i for i in load("institutions")}
    raw_rows = load("raw_citation_rows")

    raw_works = []
    for w in works:
        nested_authors = []
        for ah in authorships_by_work.get(w["record_id"], []):
            a = authors.get(ah["author_key"], {})
            first, last = _split_name(a.get("display_name", ""))
            ror = ah.get("institution_ror")
            inst = institutions.get(ror, {}) if ror else {}
            nested_authors.append({
                "openalex_id": a.get("openalex_id"),
                "orcid": a.get("orcid"),
                "display_name": a.get("display_name"),
                "last_name": last,
                "first_name": first,
                "name_key": a.get("author_key"),
                "position": ah.get("position"),
                "institution_ror": ror,
                "institution_name": inst.get("name") if inst else None,
                "country_code": inst.get("country_code") if inst else None,
                "raw_affiliation": ah.get("raw_affiliation"),
            })
        raw_works.append({
            "record_id": w["record_id"],
            "title": w.get("title"),
            "doi": w.get("doi"),
            "pmid": w.get("pmid"),
            "pmcid": w.get("pmcid"),
            "year": w.get("year"),
            "venue": w.get("venue"),
            "pub_type": w.get("pub_type"),
            "is_preprint": w.get("is_preprint"),
            "is_retracted": w.get("is_retracted"),
            "mesh_terms": w.get("mesh_terms") or [],
            "source": w.get("source"),
            "retrieved_at": w.get("retrieved_at"),
            "is_synthetic": w.get("is_synthetic"),
            "openalex_id": w.get("openalex_id"),
            "authors": nested_authors,
        })
    return raw_works, raw_rows, dict(ROR_ALIASES)
