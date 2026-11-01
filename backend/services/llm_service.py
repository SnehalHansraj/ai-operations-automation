"""
LLM Service — pluggable provider layer.

Supported providers:
- mock      -> deterministic fallback for testing
- ollama    -> local LLM using Ollama
- litellm   -> same local model, called through LiteLLM's unified API
- openai   -> optional cloud provider
- anthropic -> optional cloud provider

The rest of the application only interacts with:
    classify_and_extract()
    generate_response()
"""

import json
import os
import re
from typing import Any

import requests


LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434",
).rstrip("/")

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen3:4b",
)

# LiteLLM model string. "ollama_chat/<model>" targets Ollama's /api/chat.
# Swap to e.g. "gpt-4o-mini" or "anthropic/claude-sonnet-4-6" to change
# provider without touching any other code.
LITELLM_MODEL = os.getenv(
    "LITELLM_MODEL",
    f"ollama_chat/{OLLAMA_MODEL}",
)


ISSUE_TYPES = [
    "delayed_delivery",
    "damaged_item",
    "wrong_item",
    "refund_request",
    "cancellation",
    "general_inquiry",
]


ISSUE_KEYWORDS = {
    "delayed_delivery": [
        "hasn't arrived",
        "not arrived",
        "delayed",
        "late",
        "still waiting",
        "where is my",
    ],
    "damaged_item": [
        "damaged",
        "broken",
        "smashed",
        "cracked",
    ],
    "wrong_item": [
        "wrong item",
        "wrong product",
        "incorrect item",
    ],
    "refund_request": [
        "refund",
        "money back",
        "reimburse",
    ],
    "cancellation": [
        "cancel my order",
        "cancel order",
    ],
}


ORDER_ID_PATTERN = re.compile(r"#?\b(\d{4,10})\b")


# -------------------------------------------------------------------
# MOCK PROVIDER
# -------------------------------------------------------------------

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
            "Thanks for reaching out. Your order {order_id} is currently "
            "'{status}'. We're sorry for the delay — the latest scan shows "
            "it at {location}, with a new estimated delivery of {eta}. "
            "We'll keep monitoring it."
        ),
        "damaged_item": (
            "We're sorry to hear order {order_id} arrived damaged. "
            "A replacement is being arranged automatically and you'll "
            "receive a confirmation shortly."
        ),
        "wrong_item": (
            "Apologies — order {order_id} was flagged as the wrong item. "
            "A correction and return label are being generated now."
        ),
        "refund_request": (
            "Your refund request for order {order_id} has been logged "
            "and forwarded to the billing queue for processing."
        ),
        "cancellation": (
            "Order {order_id} has been flagged for cancellation. "
            "You'll get a confirmation once it's been stopped in the warehouse."
        ),
        "general_inquiry": (
            "Thanks for your message about order {order_id}. "
            "Our team has logged it and will follow up shortly with more detail."
        ),
    }

    template = templates.get(
        issue_type,
        templates["general_inquiry"],
    )

    return template.format(
        order_id=order_status.get("order_id", "N/A"),
        status=order_status.get("status", "unknown"),
        location=order_status.get("last_location", "in transit"),
        eta=order_status.get("eta", "TBD"),
    )


# -------------------------------------------------------------------
# OLLAMA HELPERS
# -------------------------------------------------------------------

def _ollama_chat(
    messages: list[dict[str, str]],
    temperature: float = 0.0,
) -> str:
    """
    Send a chat request to the locally running Ollama server.
    """

    url = f"{OLLAMA_BASE_URL}/api/chat"

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=120,
        )

        response.raise_for_status()

    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            "Could not connect to Ollama. "
            "Make sure Ollama is running and available at "
            f"{OLLAMA_BASE_URL}"
        ) from exc

    except requests.exceptions.Timeout as exc:
        raise RuntimeError(
            "Ollama request timed out. "
            "The local model may be taking too long to respond."
        ) from exc

    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(
            f"Ollama returned an HTTP error: {response.status_code} "
            f"{response.text}"
        ) from exc

    data = response.json()

    try:
        return data["message"]["content"].strip()
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            f"Unexpected Ollama response: {data}"
        ) from exc


# -------------------------------------------------------------------
# LITELLM HELPER
# -------------------------------------------------------------------

def _litellm_chat(
    messages: list[dict[str, str]],
    temperature: float = 0.0,
) -> str:
    """
    Same contract as _ollama_chat, but routed through LiteLLM.

    LiteLLM gives one OpenAI-style interface for 100+ providers, so the
    model can be changed via LITELLM_MODEL alone.
    """

    import litellm  # imported lazily so other providers don't need it

    kwargs: dict[str, Any] = {
        "model": LITELLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "timeout": 120,
    }

    if LITELLM_MODEL.startswith(("ollama/", "ollama_chat/")):
        kwargs["api_base"] = OLLAMA_BASE_URL

    try:
        response = litellm.completion(**kwargs)
    except Exception as exc:
        raise RuntimeError(
            f"LiteLLM call to '{LITELLM_MODEL}' failed: {exc}"
        ) from exc

    content = (response.choices[0].message.content or "").strip()

    # Qwen3 may emit <think>...</think> before the answer; drop it.
    content = re.sub(
        r"<think>.*?</think>",
        "",
        content,
        flags=re.DOTALL,
    ).strip()

    if not content:
        raise RuntimeError(
            f"LiteLLM returned an empty response from '{LITELLM_MODEL}'"
        )

    return content


def _extract_json(raw_text: str) -> dict[str, Any]:
    """
    Safely extract JSON from an LLM response.

    Handles responses such as:
        {"issue_type": "..."}
    and markdown fenced JSON.
    """

    cleaned = raw_text.strip()

    # Remove markdown code fences if the model adds them.
    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
    )

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try finding the first JSON object in the response.
    match = re.search(
        r"\{.*\}",
        cleaned,
        flags=re.DOTALL,
    )

    if not match:
        raise ValueError(
            f"Could not extract JSON from LLM response: {raw_text}"
        )

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON returned by LLM: {raw_text}"
        ) from exc


def _validate_classification(data: dict) -> dict:
    """
    Validate and normalize the classification returned by the LLM.
    """

    issue_type = data.get("issue_type", "general_inquiry")

    if issue_type not in ISSUE_TYPES:
        issue_type = "general_inquiry"

    order_id = data.get("order_id")

    if order_id is not None:
        order_id = str(order_id)

        # Keep only digits.
        order_id = re.sub(r"\D", "", order_id)

        if not order_id:
            order_id = None

    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5

    confidence = max(
        0.0,
        min(1.0, confidence),
    )

    return {
        "issue_type": issue_type,
        "order_id": order_id,
        "confidence": confidence,
    }


# -------------------------------------------------------------------
# OLLAMA CLASSIFICATION
# -------------------------------------------------------------------

def _ollama_classify_and_extract(text: str, chat_fn=None) -> dict:
    """
    Use the local Qwen model to classify the customer request
    and extract an order ID.
    """

    system_prompt = """
You are an operations request classification assistant.

Your job is to analyze a customer request and return ONLY valid JSON.

Allowed issue_type values:

- delayed_delivery
- damaged_item
- wrong_item
- refund_request
- cancellation
- general_inquiry

Rules:

1. Identify the most appropriate issue_type.
2. Extract the order number if one exists.
3. order_id must contain digits only.
4. If there is no order number, use null.
5. confidence must be a number between 0 and 1.
6. Do not include markdown.
7. Do not include explanations outside the JSON.

Required JSON format:

{
  "issue_type": "delayed_delivery",
  "order_id": "12345",
  "confidence": 0.95
}
""".strip()

    user_prompt = f"""
Customer request:

{text}
""".strip()

    chat_fn = chat_fn or _ollama_chat

    raw_response = chat_fn(
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        temperature=0.0,
    )

    data = _extract_json(raw_response)

    return _validate_classification(data)


# -------------------------------------------------------------------
# PUBLIC CLASSIFICATION FUNCTION
# -------------------------------------------------------------------

def classify_and_extract(text: str) -> dict:
    """
    Returns:

    {
        "issue_type": str,
        "order_id": str | None,
        "confidence": float
    }
    """

    if LLM_PROVIDER == "mock":
        return _mock_classify_and_extract(text)

    if LLM_PROVIDER == "ollama":
        return _ollama_classify_and_extract(text)

    if LLM_PROVIDER == "litellm":
        return _ollama_classify_and_extract(
            text,
            chat_fn=_litellm_chat,
        )

    if LLM_PROVIDER == "openai":
        from openai import OpenAI

        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )

        prompt = (
            "Extract JSON with keys issue_type "
            "(one of: delayed_delivery, damaged_item, wrong_item, "
            "refund_request, cancellation, general_inquiry), "
            "order_id (digits only or null), "
            "confidence (0-1 float) from this customer message. "
            "Return ONLY JSON.\n\n"
            "Message: " + text
        )

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0,
        )

        return _validate_classification(
            json.loads(resp.choices[0].message.content)
        )

    if LLM_PROVIDER == "anthropic":
        import anthropic

        client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

        prompt = (
            "Extract JSON with keys issue_type "
            "(one of: delayed_delivery, damaged_item, wrong_item, "
            "refund_request, cancellation, general_inquiry), "
            "order_id (digits only or null), "
            "confidence (0-1 float) from this customer message. "
            "Return ONLY JSON, no preamble, no markdown fences.\n\n"
            "Message: " + text
        )

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        raw = resp.content[0].text.strip()

        return _validate_classification(
            _extract_json(raw)
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER: {LLM_PROVIDER}"
    )


# -------------------------------------------------------------------
# OLLAMA RESPONSE GENERATION
# -------------------------------------------------------------------

def _ollama_generate_response(
    issue_type: str,
    order_status: dict,
) -> str:
    """
    Generate a short customer-facing response using Qwen.
    """

    system_prompt = """
You are a professional customer operations assistant.

Write a short, friendly customer-service response.

Rules:
- Keep it to 2-3 sentences.
- Be clear and helpful.
- Do not invent information.
- Only use information present in the order status.
- Do not mention that you are an AI.
""".strip()

    user_prompt = (
        f"Issue type: {issue_type}\n\n"
        f"Order information:\n"
        f"{json.dumps(order_status, indent=2)}\n\n"
        "Write the customer response."
    )

    return _ollama_chat(
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        temperature=0.4,
    )


# -------------------------------------------------------------------
# PUBLIC RESPONSE GENERATION FUNCTION
# -------------------------------------------------------------------

def generate_response(
    issue_type: str,
    order_status: dict,
) -> str:
    """
    Generate a controlled operational response.

    We intentionally do NOT call the LLM here for normal cases.

    Reason:
    - Order information is structured.
    - Business rules already determined the allowed action.
    - A deterministic response is faster and safer.
    - The LLM is still used earlier for understanding the
      unstructured customer request.

    This reduces local-model latency significantly.
    """

    order_id = order_status.get("order_id", "N/A")
    status = order_status.get("status", "unknown")
    location = order_status.get(
        "last_location",
        "the current processing location",
    )
    eta = order_status.get(
        "eta",
        "TBD",
    )

    days_since_expected = order_status.get(
        "days_since_expected"
    )

    # ---------------------------------------------------------------
    # Delayed delivery
    # ---------------------------------------------------------------

    if issue_type == "delayed_delivery":

        if days_since_expected is not None and days_since_expected > 0:

            return (
                f"Thanks for reaching out about order #{order_id}. "
                f"Your shipment is currently {status.replace('_', ' ')} "
                f"at {location}, and the latest estimated delivery is "
                f"{eta}. We apologize for the delay and will continue "
                f"monitoring the shipment."
            )

        return (
            f"Hi! Your order #{order_id} is currently "
            f"{status.replace('_', ' ')} at {location} and is expected "
            f"to arrive on {eta}. The shipment is currently within "
            f"the expected delivery window. Thank you for your patience."
        )

    # ---------------------------------------------------------------
    # Damaged item
    # ---------------------------------------------------------------

    if issue_type == "damaged_item":

        return (
            f"We're sorry that order #{order_id} arrived damaged. "
            f"Your case has been recorded and the appropriate "
            f"replacement process has been initiated."
        )

    # ---------------------------------------------------------------
    # Wrong item
    # ---------------------------------------------------------------

    if issue_type == "wrong_item":

        return (
            f"Apologies for the incorrect item in order #{order_id}. "
            f"Your case has been recorded and the correction process "
            f"has been initiated."
        )

    # ---------------------------------------------------------------
    # Refund
    # ---------------------------------------------------------------

    if issue_type == "refund_request":

        return (
            f"Your refund request for order #{order_id} has been "
            f"recorded and forwarded to the appropriate billing "
            f"process for review."
        )

    # ---------------------------------------------------------------
    # Cancellation
    # ---------------------------------------------------------------

    if issue_type == "cancellation":

        return (
            f"Your cancellation request for order #{order_id} has "
            f"been recorded. The order will be checked against its "
            f"current processing status before cancellation."
        )

    # ---------------------------------------------------------------
    # General inquiry
    # ---------------------------------------------------------------

    return (
        f"Thanks for contacting us about order #{order_id}. "
        f"Your request has been recorded and the operations team "
        f"will follow up with the relevant information."
    )