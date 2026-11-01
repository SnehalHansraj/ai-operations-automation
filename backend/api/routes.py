from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict

from backend.db import get_db
from backend.models.models import Case, AgentStep
from backend.agents.agent import run_agent

router = APIRouter()


# -------------------------------------------------------------------
# REQUEST / RESPONSE MODELS
# -------------------------------------------------------------------

class RequestIn(BaseModel):
    text: str


class CaseOut(BaseModel):
    id: str
    order_id: str | None
    issue_type: str | None
    status: str
    response_text: str | None
    processing_time_ms: float | None

    # Agent information
    confidence: float | None = None
    action: str | None = None
    decision_reason: str | None = None
    decision_explanation: str | None = None
    verified: bool | None = None
    notified_channel: str | None = None
    trace: list[dict] = []

    class Config:
        from_attributes = True


@router.post("/requests", response_model=CaseOut)
def submit_request(
    payload: RequestIn,
    db: Session = Depends(get_db),
):
    """
    Main entry point.

    The request is processed by the agent, persisted to the database,
    and the complete agent result is returned to the dashboard.
    """

    # ---------------------------------------------------------------
    # Run the agent
    # ---------------------------------------------------------------

    result = run_agent(payload.text)

    # ---------------------------------------------------------------
    # Persist the case
    # ---------------------------------------------------------------

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

    # Get generated case ID
    db.flush()

    # ---------------------------------------------------------------
    # Persist agent trace
    # ---------------------------------------------------------------

    for step in result["trace"]:

        db.add(
            AgentStep(
                case_id=case.id,
                step_number=step["step_number"],
                step_name=step["step_name"],
                detail=step["detail"],
                duration_ms=step["duration_ms"],
            )
        )

    db.commit()

    db.refresh(case)

    # ---------------------------------------------------------------
    # Return complete agent result to dashboard
    # ---------------------------------------------------------------

    return {
        "id": case.id,
        "order_id": case.order_id,
        "issue_type": case.issue_type,
        "status": case.status,
        "response_text": case.response_text,
        "processing_time_ms": case.processing_time_ms,

        "confidence": result.get("confidence"),
        "action": result.get("action"),
        "decision_reason": result.get("decision_reason"),
        "decision_explanation": result.get(
            "decision_explanation"
        ),
        "verified": result.get("verified"),
        "notified_channel": result.get(
            "notified_channel"
        ),
        "trace": result.get("trace", []),
    }

# -------------------------------------------------------------------
# GET SINGLE CASE
# -------------------------------------------------------------------

@router.get("/cases/{case_id}")
def get_case(
    case_id: str,
    db: Session = Depends(get_db),
):
    """
    Return complete case information including the agent trace.
    """

    case = (
        db.query(Case)
        .filter(Case.id == case_id)
        .first()
    )

    if not case:
        return {"error": "not found"}

    trace = [
        {
            "step_number": s.step_number,
            "step_name": s.step_name,
            "detail": s.detail,
            "duration_ms": s.duration_ms,
        }
        for s in sorted(
            case.steps,
            key=lambda s: s.step_number,
        )
    ]

    # Try to reconstruct useful decision information
    # from the persisted execution trace.
    decision_step = next(
        (
            step
            for step in trace
            if step["step_name"] == "agent_decision"
        ),
        None,
    )

    verification_step = next(
        (
            step
            for step in trace
            if step["step_name"] == "verify_outcome"
        ),
        None,
    )

    return {
        "id": case.id,
        "raw_text": case.raw_text,
        "order_id": case.order_id,
        "issue_type": case.issue_type,
        "status": case.status,
        "response_text": case.response_text,
        "processing_time_ms": case.processing_time_ms,

        # Decision information reconstructed from the trace
        "decision": {
            "action": (
                "escalate"
                if case.status == "escalated"
                else "auto_resolve"
            ),
            "detail": (
                decision_step["detail"]
                if decision_step
                else None
            ),
        },

        "verification": (
            verification_step["detail"]
            if verification_step
            else None
        ),

        "trace": trace,
    }


# -------------------------------------------------------------------
# LIST CASES
# -------------------------------------------------------------------

@router.get("/cases")
def list_cases(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    Return recent operational cases.
    """

    # Keep the limit within a sensible range.
    limit = max(1, min(limit, 100))

    cases = (
        db.query(Case)
        .order_by(Case.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": c.id,
            "order_id": c.order_id,
            "issue_type": c.issue_type,
            "status": c.status,
            "processing_time_ms": c.processing_time_ms,
            "created_at": (
                c.created_at.isoformat()
                if c.created_at
                else None
            ),
        }
        for c in cases
    ]


# -------------------------------------------------------------------
# METRICS
# -------------------------------------------------------------------

@router.get("/metrics")
def metrics(
    db: Session = Depends(get_db),
):
    """
    Operational metrics for the OpsPilot dashboard.
    """

    total = (
        db.query(func.count(Case.id))
        .scalar()
        or 0
    )

    if total == 0:
        return {
            "cases_processed": 0,
            "avg_processing_time_ms": None,
            "avg_manual_baseline_ms": None,
            "time_saved_pct": None,
            "escalation_rate_pct": None,
            "auto_resolution_rate_pct": None,
            "issue_type_breakdown": {},
        }

    avg_auto = (
        db.query(func.avg(Case.processing_time_ms))
        .scalar()
        or 0
    )

    avg_manual = (
        db.query(func.avg(Case.manual_baseline_ms))
        .scalar()
        or 0
    )

    escalated = (
        db.query(func.count(Case.id))
        .filter(Case.status == "escalated")
        .scalar()
        or 0
    )

    resolved = (
        db.query(func.count(Case.id))
        .filter(Case.status == "resolved")
        .scalar()
        or 0
    )

    breakdown_rows = (
        db.query(
            Case.issue_type,
            func.count(Case.id),
        )
        .group_by(Case.issue_type)
        .all()
    )

    time_saved_pct = (
        round(
            100 * (1 - (avg_auto / avg_manual)),
            1,
        )
        if avg_manual
        else None
    )

    escalation_rate_pct = round(
        100 * escalated / total,
        1,
    )

    auto_resolution_rate_pct = round(
        100 * resolved / total,
        1,
    )

    return {
        "cases_processed": total,
        "avg_processing_time_ms": round(
            avg_auto,
            1,
        ),
        "avg_manual_baseline_ms": round(
            avg_manual,
            1,
        ),
        "time_saved_pct": time_saved_pct,
        "escalation_rate_pct": escalation_rate_pct,
        "auto_resolution_rate_pct": auto_resolution_rate_pct,
        "issue_type_breakdown": {
            k: v
            for k, v in breakdown_rows
        },
    }