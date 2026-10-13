"""GET /waterfall — PRD 12."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import WaterfallOut
from app.services.report_view import waterfall_view

router = APIRouter(tags=["waterfall"])


@router.get("/waterfall", response_model=WaterfallOut)
def get_waterfall(scope_type: str = Query(...), scope_id: int = Query(...),
                  policy_id: int | None = Query(None), db: Session = Depends(get_db)):
    try:
        return waterfall_view(db, scope_type, scope_id, policy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
