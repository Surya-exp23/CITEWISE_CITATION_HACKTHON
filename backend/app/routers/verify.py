"""Public report verification — PRD 12. Read-only, no auth."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Report
from app.schemas import VerifyOut
from app.services.evidence import verify_report_payload

router = APIRouter(tags=["verify"])


@router.get("/verify/{report_id}", response_model=VerifyOut)
def verify_report(report_id: int, db: Session = Depends(get_db)):
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"report {report_id} not found")
    return verify_report_payload(report.payload or {})
