import asyncio
import logging
import os
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.rag_manager import get_rag_system
from app.models import Document
from app.rag.tools import invalidate_knowledge_base_description

logger = logging.getLogger(__name__)


async def remove_document(db: Session, document: Document) -> None:
    document_id = document.id
    filename = document.filename
    # 先刪除文件列再移除索引片段：進行中的索引寫入持鎖後會確認文件仍存在，
    # 順序反過來的話，刪除片段之後才完成的寫入會把片段寫回知識庫
    db.delete(document)
    db.commit()
    invalidate_knowledge_base_description()
    try:
        rag_system = get_rag_system()
        await asyncio.to_thread(rag_system.remove_document_by_id, document_id)
    except Exception as e:
        logger.warning("Failed to remove document from RAG system: %s", str(e))
    try:
        file_path = os.path.join(settings.UPLOAD_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.warning("Failed to remove physical file: %s", str(e))
