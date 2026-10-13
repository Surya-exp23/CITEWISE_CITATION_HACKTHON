"""Policy endpoints — PRD 12. PUT recomputes classifications live and bumps the version."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Policy
from app.schemas import PolicyCreate, PolicyOut, PolicyUpdate
from app.services.policy import create_policy, get_policy, update_policy

router = APIRouter(tags=["policies"])

_ALLOWED_KEYS = {
    "citing_authors_considered": {"any", "first_last"},
    "self_citation_scope": {"author", "any_shared_author"},
    "headline_metric": {"external_only", "external_plus_internal"},
}


def _to_out(p: Policy) -> dict:
    return {"id": p.id, "institution_id": p.institution_id, "name": p.name,
            "version": p.version, "config": p.config or {}, "is_active": p.is_active}


@router.get("/policies", response_model=list[PolicyOut])
def list_policies(db: Session = Depends(get_db)):
    return [_to_out(p) for p in db.query(Policy).order_by(Policy.id).all()]


@router.post("/policies", response_model=PolicyOut, status_code=201)
def create_new_policy(body: PolicyCreate, db: Session = Depends(get_db)):
    policy = create_policy(db, name=body.name, config=body.config, institution_id=body.institution_id)
    db.commit()
    return _to_out(policy)


@router.put("/policies/{policy_id}", response_model=PolicyOut)
def update_existing_policy(policy_id: int, body: PolicyUpdate, db: Session = Depends(get_db)):
    for key, value in (body.config or {}).items():
        allowed = _ALLOWED_KEYS.get(key)
        if allowed is not None and value not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"invalid value {value!r} for {key}; allowed: {sorted(allowed)}")
    try:
        policy = update_policy(db, policy_id, body.config or {})
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    db.commit()
    return _to_out(policy)
