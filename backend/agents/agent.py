"""
OpsPilot AI Operations Agent

This module orchestrates the complete operational workflow:

    Customer Request
          ↓
    Understand Request
          ↓
    Order Status Tool
          ↓
    Operations Policy Tool
          ↓
    Agent Decision
       ↙       ↘
    Resolve   Escalate
       ↓         ↓
    Response   Human Review
                  ↓
             Notification
                  ↓
             Verification

The agent records every step so the dashboard can display
an auditable execution trace.
"""

import time

from backend.services import (
    llm_service,
    order_service,
    notification_service,
)


# ============================================================
# AGENT TRACE
# ============================================================

class AgentTrace:
    """
    Stores a step-by-step execution trace for one
    agent run.
    """

    def __init__(self):
        self.steps = []
        self._counter = 0

    def log(
        self,
        name: str,
        detail: str,
        duration_ms: float,
        category: str = "agent",
    ):
        self._counter += 1

        self.steps.append(
            {
                "step_number": self._counter,
                "step_name": name,
                "detail": detail,
                "duration_ms": round(
                    duration_ms,
                    2,
                ),
                "category": category,
            }
        )


# ============================================================
# TIMING HELPER
# ============================================================

def _timed(fn, *args, **kwargs):
    """
    Execute a function and measure execution time.
    """

    start = time.perf_counter()

    result = fn(
        *args,
        **kwargs,
    )

    duration_ms = (
        time.perf_counter() - start
    ) * 1000

    return result, duration_ms


# ============================================================
# TOOL: UNDERSTAND REQUEST
# ============================================================

def _tool_understand(
    trace: AgentTrace,
    raw_text: str,
):
    """
    Use the LLM to understand the customer request.
    """

    extraction, duration_ms = _timed(
        llm_service.classify_and_extract,
        raw_text,
    )

    issue_type = extraction.get(
        "issue_type",
        "general_inquiry",
    )

    order_id = extraction.get(
        "order_id"
    )

    confidence = extraction.get(
        "confidence",
        0.0,
    )

    trace.log(
        "Request Understood",
        (
            f"issue_type={issue_type} | "
            f"order_id={order_id} | "
            f"confidence={confidence}"
        ),
        duration_ms,
        "llm",
    )

    return extraction


# ============================================================
# TOOL: ORDER STATUS
# ============================================================

def _tool_order_status(
    trace: AgentTrace,
    order_id: str | None,
):
    """
    Retrieve order/shipment information.
    """

    order_status, duration_ms = _timed(
        order_service.get_order_status,
        order_id,
    )

    trace.log(
        "Order Status Tool",
        (
            f"Order {order_id} → "
            f"status={order_status.get('status')} | "
            f"location={order_status.get('last_location')} | "
            f"eta={order_status.get('eta')} | "
            f"days_since_expected="
            f"{order_status.get('days_since_expected', 0)}"
        ),
        duration_ms,
        "tool",
    )

    return order_status


# ============================================================
# TOOL: OPERATIONS POLICY
# ============================================================

def _tool_policy(
    trace: AgentTrace,
    order_status: dict,
    raw_text: str,
    issue_type: str,
):
    """
    Apply operational business rules.
    """

    rule_result, duration_ms = _timed(
        order_service.check_business_rules,
        order_status,
    )

    action = rule_result.get(
        "action",
        "escalate",
    )

    reason = rule_result.get(
        "reason",
        "unknown_reason",
    )

    trace.log(
        "Operations Policy Tool",
        (
            f"action={action} | "
            f"reason={reason}"
        ),
        duration_ms,
        "tool",
    )

    return rule_result


# ============================================================
# TOOL: GENERATE RESPONSE
# ============================================================

def _tool_generate_response(
    trace: AgentTrace,
    issue_type: str,
    order_status: dict,
    rule_result: dict,
):
    """
    Generate the customer-facing response.

    Escalated cases do not require another LLM call.
    """

    action = rule_result.get(
        "action"
    )

    reason = rule_result.get(
        "reason",
        "human_review_required",
    )

    # --------------------------------------------------------
    # ESCALATION
    # --------------------------------------------------------

    if action == "escalate":

        start = time.perf_counter()

        order_id = order_status.get(
            "order_id",
            "unknown",
        )

        response_text = (
            f"We noticed a discrepancy between "
            f"the information in your message and "
            f"our latest shipment data for order "
            f"#{order_id}. Your case has been "
            f"escalated to our operations team "
            f"for review."
        )

        duration_ms = (
            time.perf_counter() - start
        ) * 1000

        trace.log(
            "Human Escalation",
            reason,
            duration_ms,
            "escalation",
        )

        return response_text

    # --------------------------------------------------------
    # AUTO RESPONSE
    # --------------------------------------------------------

    response_text, duration_ms = _timed(
        llm_service.generate_response,
        issue_type,
        order_status,
    )

    trace.log(
        "Generate Response",
        response_text[:300],
        duration_ms,
        "llm",
    )

    return response_text


# ============================================================
# TOOL: NOTIFICATION
# ============================================================

def _tool_notify(
    trace: AgentTrace,
    case_id: str,
    issue_type: str,
    action: str,
    response_text: str,
    customer_request: str,
    order_status: dict,
    confidence: float | None,
    decision_reason: str,
):
    """
    Notify the appropriate human operations channel.

    IMPORTANT:
    order_status is explicitly passed into this function.
    This fixes the previous NameError.
    """

    start = time.perf_counter()

    channel = notification_service.notify(
        case_id=case_id,
        issue_type=issue_type,
        action=action,
        response_text=response_text,
        customer_request=customer_request,
        order_status=order_status,
        confidence=confidence,
        decision_reason=decision_reason,
    )

    duration_ms = (
        time.perf_counter() - start
    ) * 1000

    trace.log(
        "Notification Sent",
        f"channel={channel}",
        duration_ms,
        "notification",
    )

    return channel


# ============================================================
# TOOL: VERIFICATION
# ============================================================

def _tool_verify(
    trace: AgentTrace,
    response_text: str,
    channel: str,
):
    """
    Verify that the agent produced a response and
    notification processing completed.
    """

    start = time.perf_counter()

    response_created = bool(
        response_text
        and response_text.strip()
    )

    notification_processed = channel in {
        "email",
        "slack",
        "log",
    }

    verified = (
        response_created
        and notification_processed
    )

    checks = []

    if response_created:
        checks.append(
            "response_created"
        )

    if notification_processed:
        checks.append(
            "notification_processed"
        )

    duration_ms = (
        time.perf_counter() - start
    ) * 1000

    trace.log(
        "Outcome Verified",
        (
            f"verified={verified} | "
            f"checks={','.join(checks)}"
        ),
        duration_ms,
        "verification",
    )

    return verified


# ============================================================
# MAIN AGENT
# ============================================================

def run_agent(raw_text: str) -> dict:
    """
    Execute one complete OpsPilot operational case.
    """

    trace = AgentTrace()

    overall_start = time.perf_counter()

    # ========================================================
    # 1. AGENT STARTED
    # ========================================================

    trace.log(
        "Agent Started",
        f"Received request: {raw_text}",
        0.0,
        "agent",
    )

    # ========================================================
    # 2. UNDERSTAND REQUEST
    # ========================================================

    extraction = _tool_understand(
        trace,
        raw_text,
    )

    issue_type = extraction.get(
        "issue_type",
        "general_inquiry",
    )

    order_id = extraction.get(
        "order_id"
    )

    confidence = extraction.get(
        "confidence",
        0.0,
    )

    # ========================================================
    # 3. GET ORDER STATUS
    # ========================================================

    order_status = _tool_order_status(
        trace,
        order_id,
    )

    # ========================================================
    # 4. OPERATIONS POLICY
    # ========================================================

    rule_result = _tool_policy(
        trace,
        order_status,
        raw_text,
        issue_type,
    )

    action = rule_result.get(
        "action",
        "escalate",
    )

    decision_reason = rule_result.get(
        "reason",
        "unknown_reason",
    )

    # ========================================================
    # 5. AGENT DECISION
    # ========================================================

    decision_start = time.perf_counter()

    trace.log(
        "Agent Decision",
        (
            f"Decision={action} | "
            f"Reason={decision_reason}"
        ),
        (
            time.perf_counter()
            - decision_start
        ) * 1000,
        "decision",
    )

    # ========================================================
    # 6. GENERATE CUSTOMER RESPONSE
    # ========================================================

    response_text = _tool_generate_response(
        trace,
        issue_type,
        order_status,
        rule_result,
    )

    # ========================================================
    # 7. NOTIFY
    # ========================================================

    channel = _tool_notify(
        trace=trace,
        case_id=order_id or "unknown",
        issue_type=issue_type,
        action=action,
        response_text=response_text,
        customer_request=raw_text,
        order_status=order_status,
        confidence=confidence,
        decision_reason=decision_reason,
    )

    # ========================================================
    # 8. VERIFY OUTCOME
    # ========================================================

    verified = _tool_verify(
        trace,
        response_text,
        channel,
    )

    # ========================================================
    # 9. COMPLETE
    # ========================================================

    total_ms = (
        time.perf_counter()
        - overall_start
    ) * 1000

    status = (
        "escalated"
        if action == "escalate"
        else "resolved"
    )

    trace.log(
        "Agent Completed",
        (
            f"status={status} | "
            f"verified={verified}"
        ),
        0.0,
        "agent",
    )

    # ========================================================
    # FINAL RESULT
    # ========================================================

    return {
        "issue_type": issue_type,

        "order_id": order_id,

        "confidence": confidence,

        "order_status": order_status,

        "action": action,

        "decision_reason": decision_reason,

        "decision_explanation": (
            "The operational policy requires "
            "human review."
            if action == "escalate"
            else
            "The case satisfies the conditions "
            "for automatic processing."
        ),

        "response_text": response_text,

        "notified_channel": channel,

        "processing_time_ms": round(
            total_ms,
            2,
        ),

        "status": status,

        "verified": verified,

        "trace": trace.steps,
    }