import pytest

import app.api.tags as tags_module
import app.core.llm_client as llm_client
from app.services.document_processor import DocumentProcessor


@pytest.mark.asyncio
async def test_summary_uses_default_model_from_remote_list(monkeypatch):
    calls = []

    async def fake_models_and_default():
        return ["local-model"], "local-model"

    async def fake_call_llm(messages, model_name=None, timeout=None, reasoning_effort=None):
        calls.append({"model_name": model_name, "timeout": timeout})
        return "這是一份測試用的產品規格說明書，涵蓋功能、規格與使用方式等主要章節內容。"

    monkeypatch.setattr(tags_module, "models_and_default", fake_models_and_default)
    monkeypatch.setattr(llm_client, "call_llm", fake_call_llm)

    summary = await DocumentProcessor.generate_document_summary_async("spec.txt", "產品規格內容" * 20, "txt")

    assert calls == [{"model_name": "local-model", "timeout": None}]
    assert summary.startswith("測試用的產品規格說明書")
