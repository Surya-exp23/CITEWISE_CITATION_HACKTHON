"""Researcher endpoints — PRD 12."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Author
from app.schemas import PaperRow, ResearcherOut, ResearcherReport
from app.services.metrics import papers_table
from app.services.policy import ensure_default_policy
from app.services.report_view import researcher_report

router = APIRouter(tags=["researchers"])


def _paginate(q, page: int, page_size: int):
    return q.offset((page - 1) * page_size).limit(page_size).all()


@router.get("/researchers", response_model=list[ResearcherOut])
def list_researchers(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                     db: Session = Depends(get_db)):
    return _paginate(db.query(Author).order_by(Author.id), page, page_size)


@router.get("/researchers/{researcher_id}/report", response_model=ResearcherReport)
def get_researcher_report(researcher_id: int, policy_id: int | None = None,
                          db: Session = Depends(get_db)):
    try:
        return researcher_report(db, researcher_id, policy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/researchers/{researcher_id}/papers", response_model=list[PaperRow])
def get_researcher_papers(researcher_id: int, policy_id: int | None = None,
                          db: Session = Depends(get_db)):
    if db.get(Author, researcher_id) is None:
        raise HTTPException(status_code=404, detail=f"researcher {researcher_id} not found")
    policy = ensure_default_policy(db)
    if policy_id is not None:
        from app.services.policy import get_policy
        policy = get_policy(db, policy_id)
        if policy is None:
            raise HTTPException(status_code=404, detail=f"policy {policy_id} not found")
    return papers_table(db, "researcher", researcher_id, policy)
