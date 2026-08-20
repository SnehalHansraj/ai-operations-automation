"""
The Agent — orchestrates tools (LLM, Order API, business rules, notification)
to resolve one incoming request end-to-end, and records every step it took.

This is what makes it "agentic" rather than a single LLM call:
the agent decides, at runtime, which tools to call and in what order,
based on what the previous tool returned (e.g. it only escalates instead
of auto-responding when business rules say so).
"""
import time

from backend.services import llm_service, order_service, notification_service


class AgentTrace:
    """Collects step-by-step trace for one run, so it can be persisted/audited."""

    def __init__(self):
        self.steps = []
        self._counter = 0

    def log(self, name: str, detail: str, duration_ms: float):
        self._counter += 1
        self.steps.append({
            "step_number": self._counter,
            "step_name": name,
            "detail": detail,
            "duration_ms": round(duration_ms, 2),
        })


def _timed(fn, *args, **kwargs):
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    duration_ms = (time.perf_counter() - start) * 1000
    return result, duration_ms


def run_agent(raw_text: str) -> dict:
    """
    Runs the full agentic pipeline for one incoming request.

    Steps:
      1. classify + extract (LLM tool)
      2. call order/shipment API (tool)
      3. apply business rules (tool)
      4. decide + generate response (LLM tool, conditioned on rules)
      5. notify a human channel (tool)
      6. return everything + full trace + total processing time
    """
    trace = AgentTrace()
    overall_start = time.perf_counter()

    # Step 1 — classify & extract
    extraction, dur = _timed(llm_service.classify_and_extract, raw_text)
    trace.log("classify_and_extract", f"issue_type={extraction['issue_type']} order_id={extraction['order_id']} confidence={extraction['confidence']}", dur)

    order_id = extraction.get("order_id")
    issue_type = extraction.get("issue_type")

    # Step 2 — call order/shipment API
    order_status, dur = _timed(order_service.get_order_status, order_id)
    trace.log("call_order_api", f"status={order_status.get('status')} location={order_status.get('last_location')}", dur)

    # Step 3 — business rules
    rule_result, dur = _timed(order_service.check_business_rules, order_status)
    trace.log("check_business_rules", f"action={rule_result['action']} reason={rule_result['reason']}", dur)

    # Step 4 — decide + generate response
    action = rule_result["action"]
    if action == "escalate":
        response_text = (
            f"This case (order {order_id}) needs human review: {rule_result['reason']}. "
            f"It has been escalated to the ops team."
        )
        response_dur = 0.0
        trace.log("generate_response", "escalated — templated hand-off message, no LLM call needed", response_dur)
    else:
        response_text, response_dur = _timed(llm_service.generate_response, issue_type, order_status)
        trace.log("generate_response", response_text[:120], response_dur)

    # Step 5 — notify
    channel, dur = _timed(notification_service.notify, order_id or "unknown", issue_type, action, response_text)
    trace.log("notify", f"channel={channel}", dur)

    total_ms = (time.perf_counter() - overall_start) * 1000

    return {
        "issue_type": issue_type,
        "order_id": order_id,
        "confidence": extraction.get("confidence"),
        "order_status": order_status,
        "action": action,
        "response_text": response_text,
        "notified_channel": channel,
        "processing_time_ms": round(total_ms, 2),
        "status": "escalated" if action == "escalate" else "resolved",
        "trace": trace.steps,
    }
