"""Citation + evidence endpoints — PRD 12."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    Citation,
    CitationClassification,
    Work,
)

from app.schemas import CitationOut, EvidenceOut
from app.services.evidence import canonical_json, sha256_hex
from app.services.policy import ensure_default_policy

router = APIRouter(tags=["citations"])

_SCOPE_TYPES = ("researcher", "institution", "paper")


@router.get("/papers/{paper_id}/citations", response_model=list[CitationOut])
def get_paper_citations(
    paper_id: int,
    scope_type: str = Query("paper"),
    scope_id: int | None = Query(None),
    klass: str | None = Query(None, pattern="^(self|internal|external)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    if db.get(Work, paper_id) is None:
        raise HTTPException(status_code=404, detail=f"work {paper_id} not found")
    if scope_type not in _SCOPE_TYPES:
        raise HTTPException(status_code=400, detail=f"scope_type must be one of {_SCOPE_TYPES}")
    policy = ensure_default_policy(db)
    eff_scope_id = scope_id if scope_id is not None else paper_id
    q = (
        db.query(Citation, CitationClassification.klass)
        .outerjoin(
            CitationClassification,
            (CitationClassification.citation_id == Citation.id)
            & (CitationClassification.scope_type == scope_type)
            & (CitationClassification.scope_id == eff_scope_id)
            & (CitationClassification.policy_id == policy.id)
            & (CitationClassification.policy_version == policy.version),
        )
        .filter(Citation.cited_work_id == paper_id)
        .order_by(Citation.id)
    )
    if klass:
        q = q.filter(CitationClassification.klass == klass)
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    works = {w.id: w for w in db.query(Work).filter(
        Work.id.in_([c.citing_work_id for c, _ in rows] or [0])).all()}
    out = []
    for cit, kl in rows:
        cw = works.get(cit.citing_work_id)
        pw = db.get(Work, cit.cited_work_id)
        out.append({
            "id": cit.id, "citing_work_id": cit.citing_work_id, "cited_work_id": cit.cited_work_id,
            "citing_title": cw.title if cw else None, "cited_title": pw.title if pw else None,
            "year": cw.year if cw else None, "mention_count": cit.mention_count,
            "raw_rows_total": cit.raw_rows_total, "duplicates_removed": cit.duplicates_removed,
            "repeats_removed": cit.repeats_removed, "klass": kl, "intent": cit.intent,
        })
    return out


@router.get("/citations/{citation_id}/evidence", response_model=EvidenceOut)
def get_citation_evidence(citation_id: int, scope_type: str = Query("paper"),
                          scope_id: int | None = Query(None),
                          db: Session = Depends(get_db)):
    from app.services.evidence import build_report_evidence

    cit = db.get(Citation, citation_id)
    if cit is None:
        raise HTTPException(status_code=404, detail=f"citation {citation_id} not found")
    if scope_type not in ("researcher", "institution", "paper"):
        raise HTTPException(status_code=400, detail="scope_type must be researcher|institution|paper")
    eff_scope_id = scope_id if scope_id is not None else cit.cited_work_id
    policy = ensure_default_policy(db)
    # Evidence is built on demand per scope (fast: bulk-preloaded single build).
    records, _root = build_report_evidence(db, scope_type, eff_scope_id, policy)
    db.commit()
    for record in records:
        if record["citation_id"] == citation_id:
            leaf = sha256_hex(canonical_json(record))
            return {"citation_id": cit.id, "record": record, "sha256": leaf}
    raise HTTPException(status_code=404, detail=f"citation {citation_id} not in scope {scope_type}/{eff_scope_id}")
