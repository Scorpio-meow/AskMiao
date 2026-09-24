from typing import Callable, Dict, List, Tuple, Optional
import os
import json
import time
import shutil
import logging
from ..types import Document
from ..tokenizers import get_chinese_analyzer, tokenizer_signature, HAS_WHOOSH

logger = logging.getLogger(__name__)

# 建立索引時的斷詞簽章；與目前設定不同時，索引裡的詞項已不可信，需重建
SIGNATURE_FILENAME = "tokenizer_signature.json"

if HAS_WHOOSH:
    from whoosh import fields, scoring
    from whoosh.filedb.filestore import FileStorage
    from whoosh.query import Or, Term
    from whoosh.writing import AsyncWriter
else:
    fields = None
    scoring = None
    FileStorage = None
    Or = None
    Term = None
    AsyncWriter = None


class BM25StoreManager:
    """Whoosh BM25 索引；doc_id 為 rag_chunks 的 chunk_id"""

    def __init__(self, data_dir: Optional[str] = None, bm25_index_dir: Optional[str] = None):
        from app.core.config import settings
        self.data_dir = data_dir or settings.DATA_DIR
        self.bm25_index_dir = bm25_index_dir or settings.BM25_INDEX_DIR
        self.bm25_index = None
        self.bm25_searcher = None
        if HAS_WHOOSH:
            self.load_index()

    def _create_bm25_schema(self):
        if not HAS_WHOOSH:
            return None
        analyzer = get_chinese_analyzer()
        return fields.Schema(
            doc_id=fields.ID(stored=True, unique=True),
            content=fields.TEXT(stored=True, analyzer=analyzer),
            title=fields.TEXT(stored=True),
            source=fields.TEXT(stored=True),
            chunk_index=fields.NUMERIC(stored=True)
        )

    def load_index(self) -> None:
        if not HAS_WHOOSH or not os.path.exists(self.bm25_index_dir):
            if HAS_WHOOSH:
                logger.info("No BM25 index found, will create on first add")
            self.bm25_index = None
            self.bm25_searcher = None
            return

        try:
            storage = FileStorage(self.bm25_index_dir)
            self.bm25_index = storage.open_index()
            self.bm25_searcher = self.bm25_index.searcher(weighting=scoring.BM25F())
            logger.info("Loaded BM25 index")
        except Exception as e:
            logger.error(f"Failed to load BM25 index: {e}")
            self.bm25_index = None
            self.bm25_searcher = None

    def _close_searcher(self) -> None:
        if self.bm25_searcher:
            try:
                self.bm25_searcher.close()
            except Exception:
                pass
            self.bm25_searcher = None

    def _signature_path(self) -> str:
        return os.path.join(self.bm25_index_dir, SIGNATURE_FILENAME)

    def tokenizer_matches(self) -> bool:
        """索引建立時的斷詞簽章是否與目前設定相同；尚無索引時視為相同"""
        if self.bm25_index is None:
            return True
        try:
            with open(self._signature_path(), encoding="utf-8") as f:
                return json.load(f) == tokenizer_signature()
        except (FileNotFoundError, ValueError):
            return False

    def _write(self, apply: Callable, action: str) -> None:
        try:
            if self.bm25_index is None:
                os.makedirs(self.bm25_index_dir, exist_ok=True)
                storage = FileStorage(self.bm25_index_dir)
                self.bm25_index = storage.create_index(self._create_bm25_schema())
                with open(self._signature_path(), "w", encoding="utf-8") as f:
                    json.dump(tokenizer_signature(), f, ensure_ascii=False)
            self._close_searcher()

            lock_path = os.path.join(self.bm25_index_dir, "bm25_write.lock")
            try:
                from filelock import FileLock
            except Exception:
                FileLock = None

            for attempt in range(3):
                try:
                    if FileLock is not None:
                        with FileLock(lock_path, timeout=5):
                            with AsyncWriter(self.bm25_index) as writer:
                                apply(writer)
                    else:
                        with AsyncWriter(self.bm25_index) as writer:
                            apply(writer)
                    break
                except Exception as e:
                    logger.warning(f"BM25 {action} attempt {attempt + 1} failed: {e}")
                    time.sleep(0.3)

            try:
                self.bm25_searcher = self.bm25_index.searcher(weighting=scoring.BM25F())
            except Exception as e:
                logger.warning(f"Failed to open BM25 searcher after {action}: {e}")

        except Exception as e:
            logger.error(f"Failed to {action} BM25 index: {e}")

    def add_documents(self, chunks: Dict[int, Document]) -> None:
        if not HAS_WHOOSH or not chunks:
            return

        def apply(writer):
            for chunk_id, chunk in chunks.items():
                writer.add_document(
                    doc_id=str(chunk_id),
                    content=chunk.page_content,
                    title=chunk.metadata.get("source", ""),
                    source=chunk.metadata.get("source", ""),
                    chunk_index=chunk.metadata.get("chunk_index", 0)
                )

        self._write(apply, "add")

    def delete_ids(self, chunk_ids: List[int]) -> None:
        if not HAS_WHOOSH or not chunk_ids or self.bm25_index is None:
            return

        def apply(writer):
            for chunk_id in chunk_ids:
                writer.delete_by_term("doc_id", str(chunk_id))

        self._write(apply, "delete")

    def search(self, query: str, chunks: Dict[int, Document], top_k: int = 50) -> List[Tuple[Document, float]]:
        if not HAS_WHOOSH or not self.bm25_searcher or not self.bm25_index:
            return []

        try:
            content_field = self.bm25_index.schema["content"]
            terms = list(dict.fromkeys(content_field.process_text(query, mode="query")))
            if not terms:
                return []
            query_obj = Or([Term("content", term) for term in terms])
            results = self.bm25_searcher.search(query_obj, limit=top_k)

            bm25_results = []
            for hit in results:
                try:
                    chunk = chunks.get(int(hit["doc_id"]))
                except (KeyError, ValueError):
                    continue
                if chunk is not None:
                    bm25_results.append((chunk, float(hit.score)))

            return bm25_results
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []

    def indexed_ids(self) -> List[str]:
        if self.bm25_index is None:
            return []
        with self.bm25_index.searcher() as searcher:
            return [stored.get("doc_id") for stored in searcher.all_stored_fields()]

    def rebuild(self, chunks: Dict[int, Document]) -> None:
        self.clear()
        if chunks and HAS_WHOOSH:
            self.add_documents(chunks)

    def ensure_aligned(self, chunks: Dict[int, Document]) -> None:
        if not HAS_WHOOSH:
            return
        if not self.tokenizer_matches():
            logger.warning("BM25 索引的斷詞簽章與目前設定不同（斷詞規則、主詞典或領域詞已變更），依資料庫片段重建 BM25 索引")
            self.rebuild(chunks)
            return
        indexed = self.indexed_ids()
        expected = {str(chunk_id) for chunk_id in chunks}
        if len(indexed) != len(expected) or set(indexed) != expected:
            logger.warning(
                f"BM25 索引 ({len(indexed)} 筆) 與資料庫片段 ({len(expected)} 筆) 的 chunk_id 不一致，依資料庫片段重建 BM25 索引"
            )
            self.rebuild(chunks)

    def clear(self) -> None:
        self._close_searcher()

        if os.path.exists(self.bm25_index_dir):
            try:
                shutil.rmtree(self.bm25_index_dir)
            except Exception as e:
                logger.warning(f"Failed to remove BM25 index dir: {e}")

        self.bm25_index = None
        logger.info("BM25 store cleared")
