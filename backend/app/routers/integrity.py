"""Integrity flags endpoint — PRD 12."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import IntegrityFlagOut
from app.services.integrity import detect_integrity_flags
from app.services.policy import ensure_default_policy

router = APIRouter(tags=["integrity"])

_SCOPE_TYPES = ("researcher", "institution")


@router.get("/integrity", response_model=list[IntegrityFlagOut])
def get_integrity_flags(scope_type: str = Query(...), scope_id: int = Query(...),
                        db: Session = Depends(get_db)):
    if scope_type not in _SCOPE_TYPES:
        raise HTTPException(status_code=400, detail=f"scope_type must be one of {_SCOPE_TYPES}")
    policy = ensure_default_policy(db)
    return detect_integrity_flags(db, scope_type, scope_id, policy)
