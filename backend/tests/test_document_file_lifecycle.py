import importlib.util
import io
import time
from pathlib import Path

import pytest
from starlette.datastructures import Headers, UploadFile

from app.api import admin as admin_api
from app.api import documents as documents_api
from app.core.config import settings
from app.models import Document as DbDocument, RagChunk
from app.rag import tools as tools_module
from app.services import document_removal
from test_rag_index_consistency import (
    LEAVE,
    OVERTIME,
    add_indexed_document,
    assert_indices_match_database,
    bm25_sources,
    index_dir,
    make_rag,
    rag,
    session_factory,
)


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(directory))
    monkeypatch.setattr(documents_api, "UPLOAD_DIR", str(directory))
    return directory


@pytest.fixture
def served_rag(rag, monkeypatch):
    monkeypatch.setattr(documents_api, "get_rag_system", lambda: rag)
    monkeypatch.setattr(document_removal, "get_rag_system", lambda: rag)
    return rag


@pytest.fixture
def offline_summary(monkeypatch):
    async def fake_summary(filename, content, file_type="", extraction=None):
        return f"summary of {filename}"

    monkeypatch.setattr(documents_api.DocumentProcessor, "generate_document_summary_async", fake_summary)


def text_upload(filename, text):
    return UploadFile(
        file=io.BytesIO(text.encode("utf-8")),
        filename=filename,
        headers=Headers({"content-type": "text/plain"}),
    )


def stored_documents(session_factory):
    with session_factory() as session:
        return [(doc.id, doc.filename, doc.is_processed) for doc in session.query(DbDocument).order_by(DbDocument.id)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "delete_endpoint",
    [documents_api.delete_document, admin_api.delete_document],
    ids=["documents", "admin"],
)
async def test_delete_endpoints_remove_upload_file(delete_endpoint, served_rag, session_factory, upload_dir):
    (upload_dir / "overtime.txt").write_text(OVERTIME, encoding="utf-8")
    (upload_dir / "leave.txt").write_text(LEAVE, encoding="utf-8")
    add_indexed_document(served_rag, session_factory, 1, "overtime.txt", OVERTIME)
    add_indexed_document(served_rag, session_factory, 2, "leave.txt", LEAVE)

    with session_factory() as db:
        await delete_endpoint(1, db=db, current_user={"username": "admin"})

    assert [path.name for path in upload_dir.iterdir()] == ["leave.txt"]
    assert [doc_id for doc_id, _, _ in stored_documents(session_factory)] == [2]
    assert bm25_sources(served_rag, "approval") == []
    assert_indices_match_database(served_rag, session_factory)


@pytest.mark.asyncio
async def test_upload_failure_after_commit_removes_row_chunks_and_upload_file(
    served_rag, session_factory, upload_dir, offline_summary, monkeypatch
):
    index_documents = served_rag.add_documents

    def index_then_fail(docs):
        index_documents(docs)
        raise RuntimeError("index save failed")

    monkeypatch.setattr(served_rag, "add_documents", index_then_fail)

    with session_factory() as db:
        response = await documents_api.upload_document(
            file=[text_upload("overtime.txt", OVERTIME)], db=db, user_id=1, current_user={"username": "admin"}
        )

    assert [(item["status"], item["http_status"]) for item in response["results"]] == [("failed", 500)]
    assert list(upload_dir.iterdir()) == []
    assert stored_documents(session_factory) == []
    with session_factory() as session:
        assert session.query(RagChunk).count() == 0
    assert bm25_sources(served_rag, "approval") == []
    assert_indices_match_database(served_rag, session_factory)


@pytest.mark.asyncio
async def test_upload_failure_keeps_upload_file_of_earlier_document(
    served_rag, session_factory, upload_dir, offline_summary, monkeypatch
):
    validate_file_type = documents_api.DocumentProcessor.validate_file_type

    def validate_or_crash(content_type, filename=None):
        if filename == "broken.txt":
            raise RuntimeError("validator crashed")
        return validate_file_type(content_type, filename)

    monkeypatch.setattr(documents_api.DocumentProcessor, "validate_file_type", validate_or_crash)

    with session_factory() as db:
        response = await documents_api.upload_document(
            file=[text_upload("overtime.txt", OVERTIME), text_upload("broken.txt", LEAVE)],
            db=db, user_id=1, current_user={"username": "admin"},
        )

    assert [(item["status"], item["http_status"]) for item in response["results"]] == [("success", 201), ("failed", 500)]
    assert [path.name for path in upload_dir.iterdir()] == ["overtime.txt"]
    assert [(filename, is_processed) for _, filename, is_processed in stored_documents(session_factory)] == [
        ("overtime.txt", True)
    ]
    assert_indices_match_database(served_rag, session_factory)


def load_reprocess_script():
    path = Path(__file__).resolve().parent.parent / "scripts" / "reprocess_existing_docs.py"
    spec = importlib.util.spec_from_file_location("reprocess_existing_docs_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_reprocess_script_invalidates_knowledge_base_description(
    rag, session_factory, upload_dir, offline_summary, monkeypatch
):
    add_indexed_document(rag, session_factory, 1, "overtime.txt", OVERTIME)
    script = load_reprocess_script()
    monkeypatch.setattr(script, "SessionLocal", session_factory)
    monkeypatch.setattr(script, "get_rag_system", lambda: rag)
    monkeypatch.setattr(tools_module, "_kb_description_cache", (time.monotonic(), "stale description"))

    await script.reprocess_all()

    assert tools_module._kb_description_cache is None
    assert_indices_match_database(rag, session_factory)
