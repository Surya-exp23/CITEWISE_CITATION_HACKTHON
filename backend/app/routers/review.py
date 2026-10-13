"""Review queue endpoints — PRD 12 (F11), with optional AI suggestions."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ReviewItem, WorkAlias
from app.schemas import DecisionIn, ReviewItemOut, ReviewSuggestionOut
from app.services import review as review_svc
from app.services.llm import llm_enabled, suggest_merge

router = APIRouter(tags=["review"])


def _to_out(item: ReviewItem) -> dict:
    return {
        "id": item.id, "item_type": item.item_type, "payload": item.payload or {},
        "score": float(item.score) if item.score is not None else None,
        "status": item.status,
        "decided_at": item.decided_at.isoformat() if item.decided_at else None,
    }


@router.get("/review", response_model=list[ReviewItemOut])
def list_review_items(item_type: str | None = Query(None), status: str | None = Query("pending"),
                      page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                      db: Session = Depends(get_db)):
    q = db.query(ReviewItem)
    if item_type:
        q = q.filter_by(item_type=item_type)
    if status:
        q = q.filter_by(status=status)
    items = q.order_by(ReviewItem.id).offset((page - 1) * page_size).limit(page_size).all()
    return [_to_out(i) for i in items]


@router.post("/review/{item_id}/decision")
def decide_item(item_id: int, body: DecisionIn, db: Session = Depends(get_db)):
    result = review_svc.decide_review_item(db, item_id, body.decision)
    if not result.get("ok"):
        raise HTTPException(status_code=404 if result.get("error") == "not_found" else 400,
                            detail=result.get("error"))
    db.commit()
    return result


@router.get("/review/{item_id}/suggestion", response_model=ReviewSuggestionOut)
def get_ai_suggestion(item_id: int, db: Session = Depends(get_db)):
    """LLM co-pilot suggestion for a dedup review item (F17). Human decides."""
    item = db.get(ReviewItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"review item {item_id} not found")
    suggestion = {"same_paper": False, "confidence": 0.0, "reason": "llm_unavailable"}
    if item.item_type == "dedup":
        payload = item.payload or {}
        a = db.query(WorkAlias).filter_by(raw_record_id=payload.get("record_a_id")).first()
        b = db.query(WorkAlias).filter_by(raw_record_id=payload.get("record_b_id")).first()

        def summary(al):
            return {"record_id": al.raw_record_id, "title": al.raw_title,
                    "doi": al.raw_doi, "source": al.source} if al else {}

        suggestion = suggest_merge(summary(a), summary(b))
    return {"item_id": item_id, "ai_suggestion": suggestion, "llm_enabled": llm_enabled()}
