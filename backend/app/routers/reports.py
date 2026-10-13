"""Report generation, retrieval, PDF export — PRD 12."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Author, Institution, Report
from app.schemas import ReportCreate, ReportOut
from app.services.evidence import generate_report
from app.services.policy import ensure_default_policy, get_policy
from app.services.report_pdf import build_report_pdf

router = APIRouter(tags=["reports"])


def _subject_exists(db: Session, scope_type: str, scope_id: int) -> bool:
    model = Author if scope_type == "researcher" else Institution
    return db.get(model, scope_id) is not None


@router.post("/reports", response_model=ReportOut, status_code=201)
def create_report(body: ReportCreate, db: Session = Depends(get_db)):
    if not _subject_exists(db, body.scope_type, body.scope_id):
        raise HTTPException(status_code=404,
                            detail=f"{body.scope_type} {body.scope_id} not found")
    policy = get_policy(db, body.policy_id) if body.policy_id else ensure_default_policy(db)
    if policy is None:
        raise HTTPException(status_code=404, detail=f"policy {body.policy_id} not found")
    report = generate_report(db, body.scope_type, body.scope_id, policy)
    db.commit()
    return _to_out(report)


@router.get("/reports/{report_id}", response_model=dict)
def get_report(report_id: int, db: Session = Depends(get_db)):
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"report {report_id} not found")
    return report.payload


@router.get("/reports/{report_id}/pdf")
def get_report_pdf(report_id: int, db: Session = Depends(get_db)):
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"report {report_id} not found")
    pdf = build_report_pdf(report.payload or {}, report.id)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="citewise-report-{report_id}.pdf"'})


def _to_out(report: Report) -> dict:
    return {
        "id": report.id, "scope_type": report.scope_type, "scope_id": report.scope_id,
        "policy_id": report.policy_id, "policy_version": report.policy_version,
        "root_hash": report.root_hash,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }
