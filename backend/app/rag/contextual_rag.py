from typing import List, Dict, Any, Optional, Tuple, AsyncGenerator, Callable
import os
import pickle
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from .types import Document
from .tokenizers import configure_tokenizer
from .indices.chunk_store import ChunkStore
from .indices.vector_store import VectorStoreManager
from .indices.bm25_store import BM25StoreManager
from .retrievers.hybrid import HybridRetriever, RetrievedChunk
from .pipeline import RAGPipeline
from .evaluator import RAGEvaluator, RetrievalCase

logger = logging.getLogger(__name__)


from app.core.config import settings
from app.core.domain_profile import domain_profile

class HybridContextualRAG:
    """
    RAG 核心門面（Facade），統整片段儲存、向量檢索、BM25 倒排索引、混合檢索、Cross-Encoder 重排序與生成管線。
    片段以資料庫 rag_chunks 為準，FAISS 與 BM25 皆以 chunk_id 對應，啟動時會依資料庫校正兩份索引。
    """
    def __init__(self, session_factory: Callable[[], Session], read_only: bool = False):
        self.chunk_size = settings.CHUNK_SIZE
        self.chunk_overlap = settings.CHUNK_OVERLAP
        self.similarity_threshold = settings.SIMILARITY_THRESHOLD
        self.top_k = settings.TOP_K
        self.rrf_k = settings.RRF_K
        self.rerank_top_k = settings.RERANK_TOP_K
        self.final_k = settings.FINAL_K
        self.rerank_weight = settings.RERANK_WEIGHT
        self.relevance_threshold = settings.RERANK_RELEVANCE_THRESHOLD
        self.model_name = settings.MODEL_NAME or ""
        self.data_dir = settings.DATA_DIR
        self.use_fp16 = settings.USE_FP16_QUANTIZATION
        self.force_cpu = settings.FORCE_CPU
        self.use_faiss_gpu = settings.USE_FAISS_GPU
        self.faiss_gpu_device = settings.FAISS_GPU_DEVICE

        os.makedirs(self.data_dir, exist_ok=True)
        configure_tokenizer(settings.JIEBA_DICTIONARY, domain_profile.domain_words)

        self.chunk_store = ChunkStore(session_factory)

        self.vector_store = VectorStoreManager(
            data_dir=self.data_dir,
            embedding_model=settings.EMBEDDING_MODEL,
            force_cpu=self.force_cpu,
            use_fp16=self.use_fp16,
            use_faiss_gpu=self.use_faiss_gpu,
            faiss_gpu_device=self.faiss_gpu_device,
            similarity_threshold=self.similarity_threshold,
            top_k=self.top_k,
        )


        self.bm25_store = BM25StoreManager(data_dir=self.data_dir)


        self.retriever = HybridRetriever(
            vector_store=self.vector_store,
            bm25_store=self.bm25_store,
            reranker_model=settings.RERANKER_MODEL,
            top_k=self.top_k,
            rrf_k=self.rrf_k,
            rerank_top_k=self.rerank_top_k,
            final_k=self.final_k,
            rerank_weight=self.rerank_weight,
            relevance_threshold=self.relevance_threshold,
            use_fp16=self.use_fp16,
        )


        self.pipeline = RAGPipeline(
            retriever=self.retriever,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            model_name=self.model_name,
        )


        self.evaluator = RAGEvaluator(self.retriever)

        if read_only:
            self._load_chunks_read_only()
        else:
            self._reconcile_indices()

        logger.info("HybridContextualRAG 門面模組初始化完成")

    def _reconcile_indices(self) -> None:
        """以資料庫片段為準，移除 FAISS 中多出的向量、補算缺少的向量，並校正 BM25"""
        with self.vector_store.lock:
            self.chunk_store.delete_orphans()
            chunks = self.chunk_store.load_all()
            indexed_ids = self.vector_store.ids()
            stale_ids = sorted(indexed_ids - chunks.keys())
            missing_ids = sorted(chunks.keys() - indexed_ids)

            if stale_ids:
                self.vector_store.remove(stale_ids)
            self.vector_store.chunks = chunks
            if missing_ids:
                embeddings = self.vector_store.embed([chunks[chunk_id].page_content for chunk_id in missing_ids])
                self.vector_store.add(missing_ids, embeddings, [chunks[chunk_id] for chunk_id in missing_ids])
            if stale_ids or missing_ids:
                logger.warning(
                    f"FAISS 索引已依資料庫片段校正：移除 {len(stale_ids)} 個多餘向量，補算 {len(missing_ids)} 個缺少的向量"
                )
                self.vector_store.save_indices()

            self.bm25_store.ensure_aligned(self.vector_store.chunks)

    def _load_chunks_read_only(self) -> None:
        """唯讀模式（例如離線評估）：只載入片段，不修改資料庫或索引檔；三方不一致或斷詞設定不符時拒絕執行"""
        chunks = self.chunk_store.load_all()
        expected_bm25_ids = sorted(str(chunk_id) for chunk_id in chunks)
        if self.vector_store.ids() != set(chunks) or sorted(self.bm25_store.indexed_ids()) != expected_bm25_ids:
            raise RuntimeError("索引與資料庫片段不一致；請先啟動後端完成校正，再執行唯讀評估")
        if not self.bm25_store.tokenizer_matches():
            raise RuntimeError("BM25 索引的斷詞簽章與目前設定不符；請先啟動後端完成重建，再執行唯讀評估")
        self.vector_store.chunks = chunks


    @property
    def documents(self) -> List[Document]:
        return self.vector_store.documents

    @property
    def index(self):
        return self.vector_store.index

    @property
    def embedding_dimension(self) -> int:
        return self.vector_store.embedding_dimension

    @property
    def local_embeddings(self):
        return self.vector_store.local_embeddings

    @property
    def cross_encoder(self):
        return self.retriever.cross_encoder

    @property
    def device(self):
        return self.vector_store.device

    @property
    def bm25_index(self):
        return self.bm25_store.bm25_index

    @property
    def bm25_searcher(self):
        return self.bm25_store.bm25_searcher


    def vector_search(self, query: str, top_k: int = None, apply_threshold: bool = True) -> List[Tuple[Document, float]]:
        with self.vector_store.lock:
            return self.vector_store.search(query, top_k=top_k, apply_threshold=apply_threshold)

    def bm25_search(self, query: str, top_k: int = None) -> List[Tuple[Document, float]]:
        with self.vector_store.lock:
            return self.bm25_store.search(query, self.vector_store.chunks, top_k=top_k or self.top_k)

    def smart_search(self, query: str, target_document: Optional[str] = None) -> List[RetrievedChunk]:
        return self.retriever.smart_search(query, target_document)


    def add_documents(self, documents: List[Document]) -> int:
        chunks = self.pipeline.split_documents(documents)
        if not chunks:
            return 0
        with self.vector_store.lock:
            embeddings = self.vector_store.embed([chunk.page_content for chunk in chunks])
            with self.chunk_store.session_factory() as session:
                chunk_ids = self.chunk_store.insert(session, chunks)
                self.vector_store.add(chunk_ids, embeddings, chunks)
                try:
                    session.commit()
                except Exception:
                    self.vector_store.remove(chunk_ids)
                    raise
            self.bm25_store.add_documents(dict(zip(chunk_ids, chunks)))
            self.vector_store.save_indices()
        return len(chunks)

    def remove_document_by_id(self, document_id: int) -> int:
        with self.vector_store.lock:
            chunk_ids = [
                chunk_id for chunk_id, chunk in self.vector_store.chunks.items()
                if chunk.metadata.get("document_id") == document_id
            ]
            self.chunk_store.delete_by_document(document_id)
            if chunk_ids:
                self.vector_store.remove(chunk_ids)
                self.bm25_store.delete_ids(chunk_ids)
                self.vector_store.save_indices()
        logger.info(f"Removed {len(chunk_ids)} chunks for document_id {document_id}")
        return len(chunk_ids)

    def clear_indices(self):
        with self.vector_store.lock:
            self.chunk_store.delete_all()
            self.vector_store.clear()
            self.bm25_store.clear()


    async def generate_response_stream(
        self,
        query: str,
        conversation_history: List[Dict[str, str]],
        model_name: Optional[str] = None,
        reasoning_effort: Optional[str] = "medium",
        attachments: Optional[List[Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        async for event in self.pipeline.generate_response_stream(
            query=query,
            conversation_history=conversation_history,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            attachments=attachments
        ):
            yield event


    def evaluate_retrieval(self, cases: List[RetrievalCase], k_values: List[int]) -> Dict[str, Any]:
        return self.evaluator.evaluate(cases, k_values)


    def get_statistics(self) -> Dict[str, Any]:
        bm25_status = "Available" if self.bm25_store.bm25_index else "Not Available"
        return {
            "total_documents": len(self.vector_store.chunks),
            "total_vectors": self.vector_store.index.ntotal,
            "embedding_dimension": self.vector_store.embedding_dimension,
            "bm25_status": bm25_status,
            "similarity_threshold": self.similarity_threshold,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "last_reindex": self._get_last_reindex_time()
        }

    def _get_last_reindex_time(self) -> Optional[str]:
        try:
            if os.path.exists(self.vector_store.metadata_path):
                with open(self.vector_store.metadata_path, "rb") as f:
                    metadata = pickle.load(f)
                last_reindex = metadata.get("last_reindex")
                if last_reindex and isinstance(last_reindex, datetime):
                    return last_reindex.isoformat()
        except Exception:
            pass
        return None

    def get_vector_store_info(self) -> Dict[str, Any]:
        return {
            "total_vectors": self.vector_store.index.ntotal,
            "total_documents": len(self.vector_store.chunks),
            "embedding_dimension": self.vector_store.embedding_dimension,
            "index_type": "FAISS IndexIDMap2(IndexFlatIP) + Whoosh BM25",
            "vector_index_exists": os.path.exists(self.vector_store.faiss_index_path),
            "bm25_index_exists": os.path.exists(self.bm25_store.bm25_index_dir),
            "last_reindex": self._get_last_reindex_time()
        }

    def force_reindex(self):
        logger.info("Forcing reindex...")
        with self.vector_store.lock:
            chunks = dict(self.vector_store.chunks)
            chunk_ids = list(chunks)
            embeddings = self.vector_store.embed([chunks[chunk_id].page_content for chunk_id in chunk_ids]) if chunk_ids else None
            self.vector_store.reset_index()
            if chunk_ids:
                self.vector_store.add(chunk_ids, embeddings, [chunks[chunk_id] for chunk_id in chunk_ids])
            self.bm25_store.rebuild(chunks)
            self.vector_store.save_indices()
        return True


ContextualRAG = HybridContextualRAG
