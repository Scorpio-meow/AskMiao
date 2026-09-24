import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import faiss
import numpy as np
import pytest
import torch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import admin as admin_api
from app.api import documents as documents_api
from app.core.config import settings
from app.core.domain_profile import domain_profile
from app.models import Document as DbDocument, RagChunk
from app.models.database import Base
from app.rag import tokenizers
from app.rag.contextual_rag import HybridContextualRAG
from app.rag.indices import vector_store as vector_store_module
from app.rag.indices.bm25_store import SIGNATURE_FILENAME
from app.rag.indices.vector_store import VectorStoreManager
from app.rag.retrievers import hybrid as hybrid_module
from app.rag.types import Document


class FakeEmbedder:
    dimension = 64

    def __init__(self, model_name, device=None):
        self.encoded_texts = 0

    def get_sentence_embedding_dimension(self):
        return self.dimension

    def encode(self, texts, batch_size=None, show_progress_bar=None, convert_to_numpy=True, device=None):
        self.encoded_texts += len(texts)
        vectors = np.zeros((len(texts), self.dimension), dtype="float32")
        for row, text in enumerate(texts):
            for ch in text:
                vectors[row, ord(ch) % self.dimension] += 1.0
        return vectors


class ConstantCrossEncoder:
    """把每個片段都判為相關的重排模型替身；索引一致性測試不涉及相關性判斷"""
    activation_fn = torch.nn.Sigmoid()

    def __init__(self, model_name, device=None):
        pass

    def predict(self, pairs):
        return [0.9 for _ in pairs]


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.result

    def all(self):
        return self.result


class FakeSession:
    def __init__(self, result):
        self.result = result

    def query(self, model):
        return FakeQuery(self.result)

    def add(self, obj):
        pass

    def delete(self, obj):
        pass

    def commit(self):
        pass


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rag.db'}")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    engine.dispose()


@pytest.fixture
def index_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "FAISS_INDEX_PATH", str(tmp_path / "faiss_index.bin"))
    monkeypatch.setattr(settings, "METADATA_PATH", str(tmp_path / "index_metadata.pkl"))
    monkeypatch.setattr(settings, "BM25_INDEX_DIR", str(tmp_path / "bm25_index"))
    monkeypatch.setattr(settings, "CHUNK_SIZE", 300)
    monkeypatch.setattr(settings, "CHUNK_OVERLAP", 100)
    monkeypatch.setattr(settings, "RRF_K", 60)
    monkeypatch.setattr(settings, "RERANK_TOP_K", 20)
    monkeypatch.setattr(settings, "FINAL_K", 8)
    monkeypatch.setattr(settings, "RERANK_RELEVANCE_THRESHOLD", 0.5)
    monkeypatch.setattr(settings, "JIEBA_DICTIONARY", None)
    monkeypatch.setattr(vector_store_module, "SentenceTransformer", FakeEmbedder)
    monkeypatch.setattr(hybrid_module, "CrossEncoder", ConstantCrossEncoder)
    return tmp_path


@pytest.fixture
def make_rag(index_dir, session_factory):
    return lambda: HybridContextualRAG(session_factory=session_factory)


@pytest.fixture
def rag(make_rag):
    return make_rag()


OVERTIME = "overtime requests need manager approval"
LEAVE = "annual leave depends on seniority"


def add_db_document(session_factory, document_id, filename, content):
    with session_factory() as session:
        session.add(DbDocument(id=document_id, filename=filename, content=content, file_type="text/plain"))
        session.commit()


def add_indexed_document(rag, session_factory, document_id, filename, content):
    add_db_document(session_factory, document_id, filename, content)
    rag.add_documents([Document(page_content=content, metadata={"source": filename, "document_id": document_id})])


def db_chunk_ids(session_factory):
    with session_factory() as session:
        return {row.id for row in session.query(RagChunk).all()}


def bm25_sources(rag, query):
    return [doc.metadata["source"] for doc, _ in rag.bm25_search(query)]


def assert_indices_match_database(rag, session_factory):
    expected = db_chunk_ids(session_factory)
    assert rag.vector_store.ids() == expected
    assert set(rag.vector_store.chunks) == expected
    assert sorted(int(chunk_id) for chunk_id in rag.bm25_store.indexed_ids()) == sorted(expected)


@pytest.mark.asyncio
async def test_delete_document_endpoint_removes_chunks_without_reembedding(rag, session_factory, monkeypatch):
    add_indexed_document(rag, session_factory, 1, "overtime.txt", OVERTIME)
    add_indexed_document(rag, session_factory, 2, "leave.txt", LEAVE)
    monkeypatch.setattr(documents_api, "get_rag_system", lambda: rag)
    encoded_before = rag.vector_store.local_embeddings.encoded_texts

    await documents_api.delete_document(
        1,
        db=FakeSession(SimpleNamespace(id=1, filename="rag_test_missing_overtime.txt")),
        current_user={"username": "admin"},
    )

    assert rag.vector_store.local_embeddings.encoded_texts == encoded_before
    assert [doc.metadata["document_id"] for doc in rag.documents] == [2]
    assert bm25_sources(rag, "seniority") == ["leave.txt"]
    assert bm25_sources(rag, "approval") == []
    assert_indices_match_database(rag, session_factory)


@pytest.mark.asyncio
async def test_admin_delete_document_endpoint_also_removes_chunks(rag, session_factory, monkeypatch):
    add_indexed_document(rag, session_factory, 1, "overtime.txt", OVERTIME)
    add_indexed_document(rag, session_factory, 2, "leave.txt", LEAVE)
    monkeypatch.setattr(admin_api, "get_rag_system", lambda: rag)

    await admin_api.delete_document(1, db=FakeSession(SimpleNamespace(id=1)), current_user={"username": "admin"})

    assert bm25_sources(rag, "approval") == []
    assert_indices_match_database(rag, session_factory)


@pytest.mark.asyncio
async def test_rebuild_index_endpoint_regenerates_chunks(rag, session_factory, monkeypatch):
    add_indexed_document(rag, session_factory, 9, "old.txt", "stale parking rules")
    db_documents = [
        SimpleNamespace(id=1, filename="rag_test_missing_overtime.txt", content=OVERTIME,
                        file_type="text/plain", description=None, uploaded_by=1),
        SimpleNamespace(id=2, filename="rag_test_missing_leave.txt", content=LEAVE,
                        file_type="text/plain", description=None, uploaded_by=1),
    ]

    async def fake_summary(filename, content, file_type=""):
        return f"summary of {filename}"

    monkeypatch.setattr(documents_api, "get_rag_system", lambda: rag)
    monkeypatch.setattr(documents_api.DocumentProcessor, "generate_document_summary_async", fake_summary)

    await documents_api.rebuild_index(db=FakeSession(db_documents), current_user={"username": "admin"})

    assert len(rag.documents) == 2
    assert bm25_sources(rag, "parking") == []
    assert bm25_sources(rag, "seniority") == ["rag_test_missing_leave.txt"]
    assert_indices_match_database(rag, session_factory)


def test_startup_reconciles_indices_with_database(make_rag, session_factory):
    rag = make_rag()
    add_indexed_document(rag, session_factory, 1, "overtime.txt", OVERTIME)
    add_indexed_document(rag, session_factory, 2, "leave.txt", LEAVE)
    leave_chunk_id = next(cid for cid, doc in rag.vector_store.chunks.items() if doc.metadata["document_id"] == 2)
    stale = Document(page_content="stale parking rules", metadata={"source": "stale.txt", "document_id": 1})
    rag.vector_store.remove([leave_chunk_id])
    rag.vector_store.add([999], rag.vector_store.embed([stale.page_content]), [stale])
    rag.bm25_store.add_documents({999: stale})
    rag.vector_store.save_indices()
    rag.bm25_store.bm25_searcher.close()

    reloaded = make_rag()

    assert leave_chunk_id in reloaded.vector_store.ids()
    assert 999 not in reloaded.vector_store.ids()
    assert bm25_sources(reloaded, "parking") == []
    assert bm25_sources(reloaded, "seniority") == ["leave.txt"]
    assert_indices_match_database(reloaded, session_factory)


def test_startup_removes_chunks_of_deleted_documents(make_rag, session_factory):
    rag = make_rag()
    add_indexed_document(rag, session_factory, 1, "overtime.txt", OVERTIME)
    add_indexed_document(rag, session_factory, 2, "leave.txt", LEAVE)
    with session_factory() as session:
        session.query(DbDocument).filter(DbDocument.id == 1).delete()
        session.commit()
    rag.bm25_store.bm25_searcher.close()

    reloaded = make_rag()

    assert [doc.metadata["document_id"] for doc in reloaded.documents] == [2]
    assert_indices_match_database(reloaded, session_factory)


def test_add_documents_rolls_back_database_when_index_update_fails(rag, session_factory, monkeypatch):
    add_db_document(session_factory, 1, "overtime.txt", OVERTIME)

    def failing_add(chunk_ids, embeddings, chunks):
        raise RuntimeError("faiss add failed")

    monkeypatch.setattr(rag.vector_store, "add", failing_add)

    with pytest.raises(RuntimeError, match="faiss add failed"):
        rag.add_documents([Document(page_content=OVERTIME, metadata={"source": "overtime.txt", "document_id": 1})])

    assert db_chunk_ids(session_factory) == set()


def test_unreadable_faiss_file_raises_and_keeps_file(index_dir):
    with open(settings.FAISS_INDEX_PATH, "wb") as f:
        f.write(b"not a faiss index")

    with pytest.raises(RuntimeError, match="原索引檔已保留"):
        VectorStoreManager(data_dir=str(index_dir))

    assert os.path.exists(settings.FAISS_INDEX_PATH)


def test_legacy_position_based_faiss_index_is_backed_up(index_dir):
    legacy = faiss.IndexFlatIP(FakeEmbedder.dimension)
    legacy.add(np.ones((1, FakeEmbedder.dimension), dtype="float32"))
    faiss.write_index(legacy, settings.FAISS_INDEX_PATH)

    store = VectorStoreManager(data_dir=str(index_dir))

    assert store.index.ntotal == 0
    assert not os.path.exists(settings.FAISS_INDEX_PATH)
    assert os.path.exists(f"{settings.FAISS_INDEX_PATH}.legacy.bak")


def test_failed_save_keeps_previous_index_file(make_rag, session_factory, monkeypatch):
    rag = make_rag()
    add_indexed_document(rag, session_factory, 1, "overtime.txt", OVERTIME)
    add_db_document(session_factory, 2, "leave.txt", LEAVE)

    def failing_dump(obj, file, *args, **kwargs):
        raise OSError("disk full")

    with monkeypatch.context() as patched:
        patched.setattr(vector_store_module.pickle, "dump", failing_dump)
        with pytest.raises(OSError):
            rag.add_documents([Document(page_content=LEAVE, metadata={"source": "leave.txt", "document_id": 2})])

    assert faiss.read_index(settings.FAISS_INDEX_PATH).ntotal == 1
    rag.bm25_store.bm25_searcher.close()
    reloaded = make_rag()
    assert len(reloaded.documents) == 2
    assert_indices_match_database(reloaded, session_factory)


def test_force_reindex_keeps_chunk_ids_and_metadata(index_dir, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "CHUNK_SIZE", 40)
    monkeypatch.setattr(settings, "CHUNK_OVERLAP", 0)
    rag = HybridContextualRAG(session_factory=session_factory)
    long_text = " ".join(f"clause{i} about overtime approval" for i in range(8))
    add_indexed_document(rag, session_factory, 1, "overtime.txt", long_text)
    chunk_indexes = {chunk_id: doc.metadata["chunk_index"] for chunk_id, doc in rag.vector_store.chunks.items()}
    assert len(chunk_indexes) > 1

    rag.force_reindex()

    assert {chunk_id: doc.metadata["chunk_index"] for chunk_id, doc in rag.vector_store.chunks.items()} == chunk_indexes
    assert_indices_match_database(rag, session_factory)


def test_read_only_mode_refuses_inconsistent_indices_without_writing(make_rag, session_factory):
    rag = make_rag()
    add_indexed_document(rag, session_factory, 1, "overtime.txt", OVERTIME)
    rag.bm25_store.bm25_searcher.close()
    read_only = HybridContextualRAG(session_factory=session_factory, read_only=True)
    assert [doc.metadata["document_id"] for doc in read_only.documents] == [1]
    read_only.bm25_store.bm25_searcher.close()

    with session_factory() as session:
        session.add(RagChunk(document_id=1, chunk_index=1, content="unindexed chunk", chunk_metadata="{}"))
        session.commit()
    faiss_mtime = os.path.getmtime(settings.FAISS_INDEX_PATH)

    with pytest.raises(RuntimeError, match="不一致"):
        HybridContextualRAG(session_factory=session_factory, read_only=True)

    assert os.path.getmtime(settings.FAISS_INDEX_PATH) == faiss_mtime
    assert len(db_chunk_ids(session_factory)) == 2


def test_startup_rebuilds_only_bm25_when_tokenizer_changes(make_rag, session_factory, monkeypatch):
    rag = make_rag()
    add_indexed_document(rag, session_factory, 1, "overtime.txt", OVERTIME)
    rag.bm25_store.bm25_searcher.close()
    monkeypatch.setattr(domain_profile, "domain_words", [*domain_profile.domain_words, "overtime requests"])

    reloaded = make_rag()

    assert reloaded.vector_store.local_embeddings.encoded_texts == 0
    assert reloaded.bm25_store.tokenizer_matches()
    signature_path = os.path.join(settings.BM25_INDEX_DIR, SIGNATURE_FILENAME)
    with open(signature_path, encoding="utf-8") as f:
        assert json.load(f) == tokenizers.tokenizer_signature()
    assert bm25_sources(reloaded, "approval") == ["overtime.txt"]
    assert_indices_match_database(reloaded, session_factory)


def test_read_only_mode_refuses_changed_tokenizer(make_rag, session_factory, monkeypatch):
    rag = make_rag()
    add_indexed_document(rag, session_factory, 1, "overtime.txt", OVERTIME)
    rag.bm25_store.bm25_searcher.close()
    monkeypatch.setattr(domain_profile, "domain_words", [*domain_profile.domain_words, "overtime requests"])

    with pytest.raises(RuntimeError, match="斷詞簽章"):
        HybridContextualRAG(session_factory=session_factory, read_only=True)


def load_evaluate_cli():
    path = Path(__file__).resolve().parent.parent / "scripts" / "evaluate_retrieval.py"
    spec = importlib.util.spec_from_file_location("evaluate_retrieval_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_evaluate_retrieval_cli_runs_on_index_snapshot(make_rag, session_factory, index_dir, monkeypatch, capsys):
    rag = make_rag()
    add_indexed_document(rag, session_factory, 1, "overtime.txt", OVERTIME)
    add_indexed_document(rag, session_factory, 2, "leave.txt", LEAVE)
    rag.bm25_store.bm25_searcher.close()
    golden = index_dir / "golden.jsonl"
    golden.write_text(json.dumps({"query": "seniority", "relevant_sources": ["leave.txt"]}) + "\n", encoding="utf-8")
    live_faiss_path = settings.FAISS_INDEX_PATH
    live_faiss_mtime = os.path.getmtime(live_faiss_path)
    cli = load_evaluate_cli()
    monkeypatch.setattr(cli, "SessionLocal", session_factory)
    monkeypatch.setattr(sys, "argv", [
        "evaluate_retrieval.py", "--golden", str(golden), "--k", "1", "3", "--min-mrr", "0.5",
    ])

    exit_code = cli.main()

    assert exit_code == 0
    assert "MRR：1.000" in capsys.readouterr().out
    assert os.path.getmtime(live_faiss_path) == live_faiss_mtime


def test_evaluate_retrieval_cli_compares_relevance_thresholds(make_rag, session_factory, index_dir, monkeypatch, capsys):
    rag = make_rag()
    add_indexed_document(rag, session_factory, 1, "overtime.txt", OVERTIME)
    add_indexed_document(rag, session_factory, 2, "leave.txt", LEAVE)
    rag.bm25_store.bm25_searcher.close()
    golden = index_dir / "golden.jsonl"
    golden.write_text(
        json.dumps({"query": "seniority", "relevant_sources": ["leave.txt"]}) + "\n"
        + json.dumps({"query": "parking", "relevant_sources": []}) + "\n",
        encoding="utf-8",
    )
    cli = load_evaluate_cli()
    monkeypatch.setattr(cli, "SessionLocal", session_factory)
    monkeypatch.setattr(sys, "argv", [
        "evaluate_retrieval.py", "--golden", str(golden), "--k", "1", "--relevance-thresholds", "0.5", "0.95",
    ])

    exit_code = cli.main()

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "門檻 0.5：MRR 1.000　hit@1 1.000　反例拒絕率 0.000" in out
    assert "門檻 0.95：MRR 0.000　hit@1 0.000　反例拒絕率 1.000" in out


@pytest.mark.asyncio
async def test_rag_config_endpoint_reports_retrieval_settings(rag, monkeypatch):
    monkeypatch.setattr(admin_api, "get_rag_system", lambda: rag)

    config = await admin_api.get_rag_config(current_user={"username": "admin"})

    assert config["batch_size"] == rag.vector_store.batch_size
    assert config["rrf_k"] == 60
    assert config["rerank_relevance_threshold"] == 0.5
    assert not {"hybrid_alpha", "normalization", "final_threshold"} & set(config)
