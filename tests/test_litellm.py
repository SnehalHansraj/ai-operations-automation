"""
Tests the LiteLLM provider path without Ollama or any API key.

LiteLLM's built-in `mock_response` returns a canned completion while still
going through litellm.completion(), so this covers the real code path.

    pytest tests/test_litellm.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import litellm

from backend.services import llm_service


def _patch_litellm(monkeypatch, canned: str):
    real_completion = litellm.completion
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return real_completion(**kwargs, mock_response=canned)

    monkeypatch.setattr(llm_service, "LLM_PROVIDER", "litellm")
    monkeypatch.setattr(litellm, "completion", fake_completion)
    return calls


def test_litellm_classify(monkeypatch):
    calls = _patch_litellm(
        monkeypatch,
        '{"issue_type": "damaged_item", "order_id": "#55555", "confidence": 0.93}',
    )

    result = llm_service.classify_and_extract(
        "The item in order #55555 arrived damaged."
    )

    assert result == {
        "issue_type": "damaged_item",
        "order_id": "55555",
        "confidence": 0.93,
    }
    assert calls[0]["model"] == llm_service.LITELLM_MODEL
    assert calls[0]["temperature"] == 0.0


def test_litellm_strips_qwen_think_block(monkeypatch):
    _patch_litellm(
        monkeypatch,
        "<think>The customer says it is late.</think>\n"
        '{"issue_type": "delayed_delivery", "order_id": "12345", "confidence": 0.9}',
    )

    result = llm_service.classify_and_extract("Order #12345 is late.")

    assert result["issue_type"] == "delayed_delivery"
    assert result["order_id"] == "12345"


def test_ollama_model_gets_api_base(monkeypatch):
    calls = _patch_litellm(
        monkeypatch,
        '{"issue_type": "general_inquiry", "order_id": null, "confidence": 0.5}',
    )
    monkeypatch.setattr(llm_service, "LITELLM_MODEL", "ollama_chat/qwen3:4b")

    llm_service.classify_and_extract("Hello?")

    assert calls[0]["api_base"] == llm_service.OLLAMA_BASE_URL
