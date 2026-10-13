"""Institution endpoints — PRD 12."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Institution
from app.schemas import InstitutionOut, LeaderboardRow
from app.services.metrics import leaderboard
from app.services.policy import ensure_default_policy
from app.services.report_view import institution_report

router = APIRouter(tags=["institutions"])


@router.get("/institutions", response_model=list[InstitutionOut])
def list_institutions(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                      db: Session = Depends(get_db)):
    q = db.query(Institution).order_by(Institution.id)
    return q.offset((page - 1) * page_size).limit(page_size).all()


@router.get("/institutions/{institution_id}/report")
def get_institution_report(institution_id: int, policy_id: int | None = None,
                           db: Session = Depends(get_db)):
    try:
        return institution_report(db, institution_id, policy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/institutions/{institution_id}/researchers", response_model=list[LeaderboardRow])
def get_institution_leaderboard(institution_id: int, page: int = Query(1, ge=1),
                               page_size: int = Query(50, ge=1, le=500),
                               db: Session = Depends(get_db)):
    if db.get(Institution, institution_id) is None:
        raise HTTPException(status_code=404, detail=f"institution {institution_id} not found")
    policy = ensure_default_policy(db)
    # Restrict to researchers affiliated with this institution on at least one work.
    from app.models import Authorship

    affiliated = [a.author_id for a in
                  db.query(Authorship).filter_by(institution_id=institution_id).all()]
    rows = leaderboard(db, policy, subject_ids=sorted(set(affiliated)))
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "name": r["name"], "papers": r["papers"],
            "raw_citations": r["raw_rows"], "verified_citations": r["verified_total"],
            "h_index_verified": r["h_index_verified"],
        })
    start = (page - 1) * page_size
    return out[start:start + page_size]
