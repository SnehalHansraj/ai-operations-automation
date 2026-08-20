"""
LLM Service — pluggable provider layer.

Why "mock" exists:
This whole project must be runnable and demoable with ZERO API keys, so the
default provider is a deterministic rule-based stand-in that returns the
exact same JSON *shape* a real LLM call would. Flip LLM_PROVIDER to
"openai" or "anthropic" and add a key in .env to use a real model —
no other code changes needed, because agent.py only ever talks to
`classify_and_extract()` and `generate_response()` below.
"""
import json
import os
import re

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock").lower()

ISSUE_KEYWORDS = {
    "delayed_delivery": ["hasn't arrived", "not arrived", "delayed", "late", "still waiting", "where is my"],
    "damaged_item": ["damaged", "broken", "smashed", "cracked"],
    "wrong_item": ["wrong item", "wrong product", "incorrect item"],
    "refund_request": ["refund", "money back", "reimburse"],
    "cancellation": ["cancel my order", "cancel order"],
}

ORDER_ID_PATTERN = re.compile(r"#?\b(\d{4,10})\b")


def _mock_classify_and_extract(text: str) -> dict:
    lower = text.lower()

    issue_type = "general_inquiry"
    confidence = 0.55
    for label, keywords in ISSUE_KEYWORDS.items():
        if any(k in lower for k in keywords):
            issue_type = label
            confidence = 0.9
            break

    match = ORDER_ID_PATTERN.search(text)
    order_id = match.group(1) if match else None

    return {
        "issue_type": issue_type,
        "order_id": order_id,
        "confidence": confidence,
    }


def _mock_generate_response(issue_type: str, order_status: dict) -> str:
    templates = {
        "delayed_delivery": (
            "Thanks for reaching out. Your order {order_id} is currently '{status}'. "
            "We're sorry for the delay — the latest scan shows it at {location}, "
            "with a new estimated delivery of {eta}. We'll keep monitoring it."
        ),
        "damaged_item": (
            "We're sorry to hear order {order_id} arrived damaged. A replacement "
            "is being arranged automatically and you'll receive a confirmation shortly."
        ),
        "wrong_item": (
            "Apologies — order {order_id} was flagged as the wrong item. "
            "A correction and return label are being generated now."
        ),
        "refund_request": (
            "Your refund request for order {order_id} has been logged and forwarded "
            "to the billing queue for processing."
        ),
        "cancellation": (
            "Order {order_id} has been flagged for cancellation. "
            "You'll get a confirmation once it's been stopped in the warehouse."
        ),
        "general_inquiry": (
            "Thanks for your message about order {order_id}. Our team has logged it "
            "and will follow up shortly with more detail."
        ),
    }
    template = templates.get(issue_type, templates["general_inquiry"])
    return template.format(
        order_id=order_status.get("order_id", "N/A"),
        status=order_status.get("status", "unknown"),
        location=order_status.get("last_location", "in transit"),
        eta=order_status.get("eta", "TBD"),
    )


def classify_and_extract(text: str) -> dict:
    """Returns {issue_type, order_id, confidence}."""
    if LLM_PROVIDER == "mock":
        return _mock_classify_and_extract(text)

    if LLM_PROVIDER == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        prompt = (
            "Extract JSON with keys issue_type "
            "(one of: delayed_delivery, damaged_item, wrong_item, refund_request, "
            "cancellation, general_inquiry), order_id (digits only or null), "
            "confidence (0-1 float) from this customer message. "
            "Return ONLY JSON.\n\nMessage: " + text
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return json.loads(resp.choices[0].message.content)

    if LLM_PROVIDER == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        prompt = (
            "Extract JSON with keys issue_type "
            "(one of: delayed_delivery, damaged_item, wrong_item, refund_request, "
            "cancellation, general_inquiry), order_id (digits only or null), "
            "confidence (0-1 float) from this customer message. "
            "Return ONLY JSON, no preamble, no markdown fences.\n\nMessage: " + text
        )
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip().strip("`").replace("json\n", "")
        return json.loads(raw)

    raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}")


def generate_response(issue_type: str, order_status: dict) -> str:
    if LLM_PROVIDER == "mock":
        return _mock_generate_response(issue_type, order_status)

    if LLM_PROVIDER == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        prompt = (
            f"Write a short, friendly customer-service reply (2-3 sentences) for a "
            f"'{issue_type}' case. Order status data: {json.dumps(order_status)}"
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        return resp.choices[0].message.content.strip()

    if LLM_PROVIDER == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        prompt = (
            f"Write a short, friendly customer-service reply (2-3 sentences) for a "
            f"'{issue_type}' case. Order status data: {json.dumps(order_status)}"
        )
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()

    raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}")
