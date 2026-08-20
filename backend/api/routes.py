from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.db import get_db
from backend.models.models import Case, AgentStep
from backend.agents.agent import run_agent

router = APIRouter()


class RequestIn(BaseModel):
    text: str


class CaseOut(BaseModel):
    id: str
    order_id: str | None
    issue_type: str | None
    status: str
    response_text: str | None
    processing_time_ms: float | None

    class Config:
        from_attributes = True


@router.post("/requests", response_model=CaseOut)
def submit_request(payload: RequestIn, db: Session = Depends(get_db)):
    """Main entry point: an incoming email/ticket/message goes through the agent."""
    result = run_agent(payload.text)

    case = Case(
        raw_text=payload.text,
        order_id=result["order_id"],
        issue_type=result["issue_type"],
        classification_confidence=result["confidence"],
        status=result["status"],
        response_text=result["response_text"],
        notified_channel=result["notified_channel"],
        processing_time_ms=result["processing_time_ms"],
    )
    db.add(case)
    db.flush()  # get case.id before inserting steps

    for step in result["trace"]:
        db.add(AgentStep(
            case_id=case.id,
            step_number=step["step_number"],
            step_name=step["step_name"],
            detail=step["detail"],
            duration_ms=step["duration_ms"],
        ))

    db.commit()
    db.refresh(case)
    return case


@router.get("/cases/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return {"error": "not found"}
    return {
        "id": case.id,
        "raw_text": case.raw_text,
        "order_id": case.order_id,
        "issue_type": case.issue_type,
        "status": case.status,
        "response_text": case.response_text,
        "processing_time_ms": case.processing_time_ms,
        "trace": [
            {
                "step_number": s.step_number,
                "step_name": s.step_name,
                "detail": s.detail,
                "duration_ms": s.duration_ms,
            }
            for s in sorted(case.steps, key=lambda s: s.step_number)
        ],
    }


@router.get("/cases")
def list_cases(limit: int = 50, db: Session = Depends(get_db)):
    cases = db.query(Case).order_by(Case.created_at.desc()).limit(limit).all()
    return [
        {
            "id": c.id,
            "order_id": c.order_id,
            "issue_type": c.issue_type,
            "status": c.status,
            "processing_time_ms": c.processing_time_ms,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in cases
    ]


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    """
    Aggregated automation-impact metrics — this is what the dashboard reads,
    and what answers Seven Senders' "measure what you ship" ask directly.
    """
    total = db.query(func.count(Case.id)).scalar() or 0
    if total == 0:
        return {
            "cases_processed": 0,
            "avg_processing_time_ms": None,
            "avg_manual_baseline_ms": None,
            "time_saved_pct": None,
            "escalation_rate_pct": None,
            "issue_type_breakdown": {},
        }

    avg_auto = db.query(func.avg(Case.processing_time_ms)).scalar() or 0
    avg_manual = db.query(func.avg(Case.manual_baseline_ms)).scalar() or 0
    escalated = db.query(func.count(Case.id)).filter(Case.status == "escalated").scalar() or 0

    breakdown_rows = (
        db.query(Case.issue_type, func.count(Case.id))
        .group_by(Case.issue_type)
        .all()
    )

    time_saved_pct = round(100 * (1 - (avg_auto / avg_manual)), 1) if avg_manual else None

    return {
        "cases_processed": total,
        "avg_processing_time_ms": round(avg_auto, 1),
        "avg_manual_baseline_ms": round(avg_manual, 1),
        "time_saved_pct": time_saved_pct,
        "escalation_rate_pct": round(100 * escalated / total, 1),
        "issue_type_breakdown": {k: v for k, v in breakdown_rows},
    }
