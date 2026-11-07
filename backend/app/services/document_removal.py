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
    db.delete(document)
    db.commit()
    invalidate_knowledge_base_description()
    try:
        rag_system = get_rag_system()
        await asyncio.to_thread(rag_system.remove_document_by_id, document_id)
    finally:
        try:
            file_path = os.path.join(settings.UPLOAD_DIR, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.warning("Failed to remove physical file: %s", str(e))