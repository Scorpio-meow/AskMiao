from typing import List, Tuple, Dict, Optional, Set
import os
import pickle
import logging
import threading
from datetime import datetime
import numpy as np
import faiss
from ..types import Document

logger = logging.getLogger(__name__)

MAX_CPU_THREADS = 16
MAX_INTEROP_THREADS = 4
LARGE_BATCH_CHUNK_THRESHOLD = 500

SentenceTransformer = None


class VectorStoreManager:
    """FAISS 向量索引（IndexIDMap2，id 為 rag_chunks 的 chunk_id）與記憶體中的 chunk_id → 片段對照"""

    def __init__(
        self,
        data_dir: Optional[str] = None,
        faiss_index_path: Optional[str] = None,
        metadata_path: Optional[str] = None,
        embedding_model: Optional[str] = None,
        force_cpu: bool = False,
        use_fp16: bool = False,
        use_faiss_gpu: bool = False,
        faiss_gpu_device: int = 0,
        batch_size: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
        top_k: Optional[int] = None,
    ):
        from app.core.config import settings

        self.data_dir = data_dir or settings.DATA_DIR
        self.faiss_index_path = faiss_index_path or settings.FAISS_INDEX_PATH
        self.metadata_path = metadata_path or settings.METADATA_PATH
        os.makedirs(self.data_dir, exist_ok=True)

        self.similarity_threshold = similarity_threshold if similarity_threshold is not None else settings.SIMILARITY_THRESHOLD
        self.top_k = top_k if top_k is not None else settings.TOP_K
        self.chunks: Dict[int, Document] = {}
        # 保護 chunks、FAISS 與 BM25 索引之間的一致性；讀寫兩側皆須持有
        self.lock = threading.RLock()

        import torch

        if force_cpu or not torch.cuda.is_available():
            self.device = "cpu"
            try:

                cpu_threads = min(MAX_CPU_THREADS, os.cpu_count() or 8)
                torch.set_num_threads(cpu_threads)
                torch.set_num_interop_threads(min(MAX_INTEROP_THREADS, os.cpu_count() or 4))
                logger.info(f"CPU 多執行緒加速啟用: PyTorch 執行緒數 = {cpu_threads}")
            except Exception as e:
                logger.debug(f"設定 PyTorch 執行緒失敗: {e}")
            self.batch_size = batch_size or settings.CPU_BATCH_SIZE
        else:
            self.device = "cuda"
            gpu_name = torch.cuda.get_device_name(0)
            gpu_mem = round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2)
            logger.info(f"GPU加速已啟用: {gpu_name} ({gpu_mem}GB 顯存)")
            self.batch_size = batch_size or settings.GPU_BATCH_SIZE

        model_name = embedding_model or settings.EMBEDDING_MODEL
        self.local_embeddings = self._load_embedding_model(model_name)
        if self.local_embeddings is None:
            raise RuntimeError(f"無法載入嵌入模型 ({model_name})，請檢查 EMBEDDING_MODEL 設定或 sentence-transformers 套件。")

        self.use_fp16 = use_fp16
        if self.use_fp16 and self.device == "cuda":
            try:
                self.local_embeddings = self.local_embeddings.half()
                logger.info("嵌入模型已量化為 FP16 (顯存減少 50%)")
            except Exception as e:
                logger.warning(f"FP16 量化失敗，使用 FP32: {e}")
                self.use_fp16 = False

        if hasattr(self.local_embeddings, "get_embedding_dimension"):
            self.embedding_dimension = self.local_embeddings.get_embedding_dimension()
        elif hasattr(self.local_embeddings, "get_sentence_embedding_dimension"):
            self.embedding_dimension = self.local_embeddings.get_sentence_embedding_dimension()
        else:
            raise RuntimeError(f"無法獲取嵌入模型 ({model_name}) 之向量維度")
        logger.info(f"嵌入模型已載入至 {self.device.upper()}: {model_name} (維度: {self.embedding_dimension}, 精度: {'FP16' if self.use_fp16 else 'FP32'})")

        self.use_faiss_gpu = use_faiss_gpu
        self.faiss_gpu_device = faiss_gpu_device
        self.gpu_resources = None
        if self.use_faiss_gpu and hasattr(faiss, "StandardGpuResources"):
            try:
                self.gpu_resources = faiss.StandardGpuResources()
                gpu_temp_memory = int(settings.FAISS_GPU_TEMP_MEMORY)
                self.gpu_resources.setTempMemory(gpu_temp_memory)
                logger.info(f"FAISS-GPU 資源已初始化 (設備 {self.faiss_gpu_device}, 臨時記憶體: {gpu_temp_memory / 1024**3:.1f}GB)")
            except Exception as e:
                logger.warning(f"FAISS-GPU 初始化失敗，回退到 CPU: {e}")
                self.use_faiss_gpu = False
                self.gpu_resources = None
        elif self.use_faiss_gpu:
            logger.warning("FAISS-GPU 已啟用但庫不支援 GPU，請安裝 faiss-gpu。回退到 CPU 模式。")
            self.use_faiss_gpu = False

        self.index = self._new_index()
        self.load_indices()

    @property
    def documents(self) -> List[Document]:
        return list(self.chunks.values())

    def _new_index(self):
        return faiss.IndexIDMap2(faiss.IndexFlatIP(self.embedding_dimension))

    def _load_embedding_model(self, model_name: str):
        global SentenceTransformer
        try:
            if SentenceTransformer is None:
                from sentence_transformers import SentenceTransformer as _ST
                SentenceTransformer = _ST
            return SentenceTransformer(model_name, device=self.device)
        except Exception as e:
            logger.error(f"載入 SentenceTransformer 模型 ({model_name}) 失敗: {e}")
            return None

    def load_indices(self) -> None:
        if not os.path.exists(self.faiss_index_path):
            return
        try:
            cpu_index = faiss.read_index(self.faiss_index_path)
        except Exception as e:
            raise RuntimeError(
                f"向量索引載入失敗：{e}。原索引檔已保留、未刪除；若檔案被其他程序占用，請排除後重新啟動；"
                f"若已損毀，請將 {self.faiss_index_path} 移出後重新啟動，系統會依資料庫中的片段重新計算向量"
            ) from e

        if not isinstance(cpu_index, faiss.IndexIDMap2):
            self._backup_incompatible_index(
                ".legacy.bak",
                "偵測到舊版（依位置對齊）的 FAISS 索引格式；升級後請呼叫 POST /api/documents/rebuild-index 由資料庫重建索引"
            )
            return
        if cpu_index.d != self.embedding_dimension:
            self._backup_incompatible_index(
                ".mismatch.bak",
                f"FAISS 索引維度 ({cpu_index.d}) 與目前嵌入模型維度 ({self.embedding_dimension}) 不符，將依資料庫片段重新計算向量"
            )
            return

        if self.use_faiss_gpu and self.gpu_resources:
            try:
                self.index = faiss.index_cpu_to_gpu(
                    self.gpu_resources,
                    self.faiss_gpu_device,
                    cpu_index
                )
                logger.info(f"FAISS 索引已轉換至 GPU (設備 {self.faiss_gpu_device})")
            except Exception as e:
                logger.warning(f"FAISS 索引 GPU 轉換失敗，使用 CPU: {e}")
                self.index = cpu_index
                self.use_faiss_gpu = False
        else:
            self.index = cpu_index

        logger.info(f"Loaded FAISS index with {self.index.ntotal} vectors")

    def _backup_incompatible_index(self, suffix: str, reason: str) -> None:
        backup_path = f"{self.faiss_index_path}{suffix}"
        os.replace(self.faiss_index_path, backup_path)
        logger.warning(f"{reason}（原檔已備份為 {backup_path}）")

    def save_indices(self) -> None:
        faiss_tmp_path = f"{self.faiss_index_path}.tmp"
        metadata_tmp_path = f"{self.metadata_path}.tmp"
        try:
            if self.use_faiss_gpu and self.gpu_resources:
                try:
                    cpu_index = faiss.index_gpu_to_cpu(self.index)
                    faiss.write_index(cpu_index, faiss_tmp_path)
                    logger.info("FAISS-GPU 索引已轉回 CPU 並儲存")
                except Exception as e:
                    logger.warning(f"GPU 索引轉換失敗，嘗試直接儲存: {e}")
                    faiss.write_index(self.index, faiss_tmp_path)
            else:
                faiss.write_index(self.index, faiss_tmp_path)

            from ..tokenizers import HAS_JIEBA
            metadata = {
                "last_reindex": datetime.now(),
                "total_documents": len(self.chunks),
                "total_vectors": self.index.ntotal,
                "tokenizer": "jieba" if HAS_JIEBA else "standard",
                "faiss_gpu_enabled": self.use_faiss_gpu
            }
            with open(metadata_tmp_path, "wb") as f:
                pickle.dump(metadata, f)

            os.replace(faiss_tmp_path, self.faiss_index_path)
            os.replace(metadata_tmp_path, self.metadata_path)

            logger.info(f"Saved FAISS indices with {self.index.ntotal} vectors")
        except Exception as e:
            logger.error(f"Error saving FAISS indices: {e}")
            raise

    def embed(self, texts: List[str]) -> np.ndarray:
        total_chunks = len(texts)
        logger.info(f"正在對 {total_chunks} 個文本塊計算向量嵌入 (Batch Size: {self.batch_size}, Device: {self.device})...")

        if total_chunks > LARGE_BATCH_CHUNK_THRESHOLD:
            step = max(LARGE_BATCH_CHUNK_THRESHOLD, self.batch_size * 4)
            all_embeddings = []
            for start_idx in range(0, total_chunks, step):
                end_idx = min(start_idx + step, total_chunks)
                sub_emb = self.local_embeddings.encode(
                    texts[start_idx:end_idx],
                    batch_size=self.batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                    device=self.device
                )
                all_embeddings.append(sub_emb)
                pct = int((end_idx / total_chunks) * 100)
                logger.info(f"向量編碼進度: {pct}% ({end_idx}/{total_chunks} 塊)")
            embeddings = np.vstack(all_embeddings)
        else:
            embeddings = self.local_embeddings.encode(
                texts,
                batch_size=self.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                device=self.device
            )

        embeddings = np.ascontiguousarray(embeddings, dtype="float32")
        faiss.normalize_L2(embeddings)
        return embeddings

    def add(self, chunk_ids: List[int], embeddings: np.ndarray, chunks: List[Document]) -> None:
        self.index.add_with_ids(embeddings, np.asarray(chunk_ids, dtype="int64"))
        self.chunks.update(zip(chunk_ids, chunks))
        logger.info(f"成功將 {len(chunk_ids)} 個文本塊寫入 FAISS 向量庫 (現有總向量數: {self.index.ntotal})")

    def remove(self, chunk_ids: List[int]) -> None:
        ids = np.asarray(chunk_ids, dtype="int64")
        if self.use_faiss_gpu and self.gpu_resources:
            cpu_index = faiss.index_gpu_to_cpu(self.index)
            cpu_index.remove_ids(ids)
            self.index = faiss.index_cpu_to_gpu(self.gpu_resources, self.faiss_gpu_device, cpu_index)
        else:
            self.index.remove_ids(ids)
        for chunk_id in chunk_ids:
            self.chunks.pop(chunk_id, None)

    def ids(self) -> Set[int]:
        return set(faiss.vector_to_array(self.index.id_map).tolist())

    def search(self, query: str, top_k: Optional[int] = None, apply_threshold: bool = True) -> List[Tuple[Document, float]]:
        if self.index.ntotal == 0:
            return []

        limit = top_k or self.top_k
        query_embedding = self.local_embeddings.encode(
            [query],
            batch_size=1,
            convert_to_numpy=True,
            device=self.device
        )
        query_embedding = np.ascontiguousarray(query_embedding, dtype="float32")
        faiss.normalize_L2(query_embedding)

        similarities, chunk_ids = self.index.search(query_embedding, min(limit, self.index.ntotal))

        results = []
        for similarity, chunk_id in zip(similarities[0], chunk_ids[0]):
            chunk = self.chunks.get(int(chunk_id))
            if chunk is not None and (not apply_threshold or similarity > self.similarity_threshold):
                results.append((chunk, float(similarity)))

        return results

    def reset_index(self) -> None:
        self.index = self._new_index()

    def clear(self) -> None:
        self.index = self._new_index()
        self.chunks = {}
        for path in [self.faiss_index_path, self.metadata_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.warning(f"刪除索引檔 {path} 失敗（下次啟動會依資料庫片段校正）: {e}")
        logger.info("Vector store cleared completely")
