"""POST /ingest/demo, POST /ingest/csv, GET /ingest/jobs/{id}."""
import re
import io
import itertools
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.pipeline import STAGES, run_pipeline
from app.schemas import CsvUploadOut, IngestJobOut
from app.services.demo_data import load_demo_dataset
from app.services.policy import ensure_default_policy

router = APIRouter(tags=["ingest"])

# In-memory job registry. Demo ingest runs synchronously and returns a
# completed job; the registry keeps /ingest/jobs/{id} honest for the UI stepper.
_jobs: dict[str, dict] = {}


def _register_job(stages: dict, summary: dict) -> dict:
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    job = {"id": job_id, "status": "completed", "stages": stages, "summary": summary}
    _jobs[job_id] = job
    return job


CSV_COLUMNS = [
    "citing_title", "citing_doi", "citing_year", "citing_authors", "citing_affiliations",
    "cited_title", "cited_doi", "cited_year", "cited_authors", "context_sentence",
]


def _parse_csv(content: bytes):
    """Validate columns; return (raw_works, raw_rows, errors)."""
    df = pd.read_csv(io.BytesIO(content))
    errors = []
    missing = [c for c in CSV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {', '.join(missing)}")
    works: dict[str, dict] = {}
    rows = []

    def work_key(title, doi):
        return f"doi:{str(doi).strip().lower()}" if pd.notna(doi) and str(doi).strip() else f"title:{str(title).strip().lower()[:60]}"

    _ROR_RE = re.compile(r"https?://ror\.org/([0-9a-z]{9})")

    def parse_authors(cell, affil_cell=None):
        names = [n.strip() for n in str(cell).split(";") if n.strip()] if pd.notna(cell) else []
        affils = [a.strip() for a in str(affil_cell).split(";")] if pd.notna(affil_cell) else []
        out = []
        for i, name in enumerate(names):
            parts = name.split()
            aff = affils[i] if i < len(affils) else ""
            m = _ROR_RE.search(aff or "")
            ror = f"https://ror.org/{m.group(1)}" if m else None
            inst_name = _ROR_RE.sub("", aff).strip(" -") or None
            out.append({
                "openalex_id": None, "orcid": None, "display_name": name,
                "last_name": parts[-1] if parts else "", "first_name": parts[0] if parts else "",
                "name_key": None,
                "position": "first" if i == 0 else ("last" if i == len(names) - 1 else "middle"),
                "institution_ror": ror, "institution_name": inst_name, "country_code": None,
                "raw_affiliation": aff or None,
            })
        return out


    def add_work(side: str, rec: dict, idx: int):
        title = rec.get(f"{side}_title")
        if pd.isna(title) or not str(title).strip():
            errors.append({"row": idx, "message": f"empty {side}_title"})
            return None
        key = work_key(title, rec.get(f"{side}_doi"))
        if key not in works:
            try:
                year = int(rec[f"{side}_year"]) if pd.notna(rec.get(f"{side}_year")) else None
            except (ValueError, TypeError):
                year = None
                errors.append({"row": idx, "message": f"bad {side}_year"})
            doi = str(rec[f"{side}_doi"]).strip() if pd.notna(rec.get(f"{side}_doi")) else None
            # medRxiv/bioRxiv DOIs (10.1101/…) are preprints even without a venue column
            is_preprint = bool(doi and doi.lower().startswith("10.1101/"))
            works[key] = {
                "record_id": f"CSV-{side}-{len(works) + 1}",
                "title": str(title).strip(),
                "doi": doi,
                "pmid": None, "pmcid": None, "year": year, "venue": None,
                "pub_type": "preprint" if is_preprint else "article",
                "is_preprint": is_preprint, "is_retracted": False,
                "mesh_terms": [], "source": "medrxiv" if is_preprint else "csv",
                "retrieved_at": None, "is_synthetic": False,
                "openalex_id": None,
                "authors": parse_authors(rec.get(f"{side}_authors"), rec.get(f"{side}_affiliations")),
            }

        return works[key]["record_id"]

    for idx, rec in enumerate(df.to_dict("records"), start=2):  # 1-based + header
        citing_id = add_work("citing", rec, idx)
        cited_id = add_work("cited", rec, idx)
        if citing_id and cited_id:
            rows.append({
                "raw_citing_record_id": citing_id,
                "raw_cited_record_id": cited_id,
                "row_kind": "mention" if pd.notna(rec.get("context_sentence")) else "reference_entry",
                "context_sentence": str(rec["context_sentence"]).strip()
                if pd.notna(rec.get("context_sentence")) else None,
                "section": None, "source": "csv", "is_synthetic": False,
            })
    return list(works.values()), rows, errors


@router.post("/ingest/demo", response_model=IngestJobOut)
def ingest_demo(db: Session = Depends(get_db)):
    raw_works, raw_rows, ror_aliases = load_demo_dataset()
    stage_log: dict = {}

    def progress(stage: str, counts: dict):
        stage_log[stage] = counts

    summary = run_pipeline(db, progress_cb=progress, raw_works=raw_works,
                           raw_rows=raw_rows, ror_aliases=ror_aliases)
    db.commit()
    job = _register_job(stage_log, summary)
    job["summary"]["policy"] = {"id": ensure_default_policy(db).id}
    return job


@router.post("/ingest/csv", response_model=CsvUploadOut)
def ingest_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail={"error": {"code": "bad_file", "message": "Upload a .csv file"}})
    content = file.file.read()
    try:
        raw_works, rows, errors = _parse_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": {"code": "csv_invalid", "message": str(exc)}})
    stage_log: dict = {}

    def progress(stage: str, counts: dict):
        stage_log[stage] = counts

    summary = run_pipeline(db, progress_cb=progress, raw_works=raw_works, raw_rows=rows)
    db.commit()
    job = _register_job(stage_log, summary)
    return {"job": job, "rows_received": len(rows), "rows_loaded": len(rows), "errors": errors}


@router.get("/ingest/jobs/{job_id}", response_model=IngestJobOut)
def ingest_job(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": f"job {job_id} not found"}})
    return job
