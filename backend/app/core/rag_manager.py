
import logging
import threading
from typing import Optional
from app.models.database import SessionLocal
from app.rag.contextual_rag import HybridContextualRAG
logger = logging.getLogger(__name__)
class RAGManager:
    _instance: Optional[HybridContextualRAG] = None
    _lock = threading.Lock()
    @classmethod
    def get_instance(cls) -> HybridContextualRAG:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    logger.info("Initializing global RAG instance...")
                    cls._instance = HybridContextualRAG(session_factory=SessionLocal)
                    logger.info("Global RAG instance initialized successfully")
        return cls._instance
def get_rag_system() -> HybridContextualRAG:
    return RAGManager.get_instance()
