import pytest

import app.core.llm_client as llm_client
from app.core.llm_client import LlmEndpoint
from app.services.document_processor import DocumentProcessor
from app.services.system_models import SystemModelTarget

SUMMARY_MODEL = SystemModelTarget(LlmEndpoint("ollama", "http://localhost:11434", None, None, False), "local-model", "medium")
CONTENT = "產品規格內容" * 20


@pytest.mark.asyncio
async def test_summary_uses_the_designated_system_model(monkeypatch):
    calls = []

    async def fake_call_llm(messages, *, endpoint, model_name, timeout=None, reasoning_effort=None):
        calls.append((endpoint, model_name, reasoning_effort))
        return "這是一份測試用的產品規格說明書，涵蓋功能、規格與使用方式等主要章節內容。"

    monkeypatch.setattr(llm_client, "call_llm", fake_call_llm)

    summary = await DocumentProcessor.generate_document_summary_async("spec.txt", CONTENT, "txt", None, SUMMARY_MODEL)

    assert calls == [(SUMMARY_MODEL.endpoint, "local-model", "medium")]
    assert summary.startswith("測試用的產品規格說明書")


@pytest.mark.asyncio
async def test_summary_without_a_system_model_uses_rules_and_calls_no_model(monkeypatch):
    async def unexpected_call(*args, **kwargs):
        raise AssertionError("未指定系統模型時不應呼叫模型")

    monkeypatch.setattr(llm_client, "call_llm", unexpected_call)

    summary = await DocumentProcessor.generate_document_summary_async("spec.txt", CONTENT, "txt", None, None)

    assert summary == DocumentProcessor._generate_fallback_summary("spec.txt", CONTENT, "txt", None)


@pytest.mark.asyncio
async def test_summary_falls_back_to_rules_when_the_system_model_fails(monkeypatch):
    async def failing_call(*args, **kwargs):
        raise RuntimeError("model offline")

    monkeypatch.setattr(llm_client, "call_llm", failing_call)

    summary = await DocumentProcessor.generate_document_summary_async("spec.txt", CONTENT, "txt", None, SUMMARY_MODEL)

    assert summary == DocumentProcessor._generate_fallback_summary("spec.txt", CONTENT, "txt", None)
