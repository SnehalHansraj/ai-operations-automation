"""
Unit tests for the agent pipeline. These don't need Docker/Postgres running —
they test the pure Python logic (LLM mock, order simulator, business rules,
and the agent orchestration) in isolation.

    pytest tests/
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("LLM_PROVIDER", "mock")

from backend.services import llm_service, order_service
from backend.agents.agent import run_agent


def test_classify_delayed_delivery():
    result = llm_service.classify_and_extract(
        "My package hasn't arrived yet. Order #12345 was supposed to arrive yesterday."
    )
    assert result["issue_type"] == "delayed_delivery"
    assert result["order_id"] == "12345"


def test_classify_damaged_item():
    result = llm_service.classify_and_extract("The item in order #55555 arrived damaged.")
    assert result["issue_type"] == "damaged_item"
    assert result["order_id"] == "55555"


def test_order_status_deterministic():
    a = order_service.get_order_status("12345")
    b = order_service.get_order_status("12345")
    assert a == b  # same order_id must always simulate the same status


def test_business_rules_no_order_id_escalates():
    rules = order_service.check_business_rules({"order_id": None})
    assert rules["action"] == "escalate"


def test_agent_end_to_end_returns_expected_shape():
    result = run_agent("My package hasn't arrived yet. Order #99999 was supposed to arrive yesterday.")
    assert result["order_id"] == "99999"
    assert result["status"] in ("resolved", "escalated")
    assert result["processing_time_ms"] > 0
    assert len(result["trace"]) >= 4
    assert result["response_text"]
