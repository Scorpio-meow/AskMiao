import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings
from app.models.database import create_tables, SessionLocal
from app.tasks.uploads_watcher import watch_missing_uploads
from app.core.rag_manager import get_rag_system
from app.api.documents import index_unprocessed_documents
from app.services.agent_skills import cleanup_staging_directories
logger = logging.getLogger(__name__)
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting ChatBot application...")
    
    await create_tables()
    cleanup_staging_directories()
    
    logger.info("Initializing global RAG system...")
    rag_system = get_rag_system()
    logger.info(f"RAG system initialized: {rag_system.get_vector_store_info()}")
    with SessionLocal() as db:
        await index_unprocessed_documents(db)
    
    uploads_watcher_task = asyncio.create_task(
        watch_missing_uploads(settings.UPLOADS_WATCHER_INTERVAL)
    )
    app.state._uploads_watcher_task = uploads_watcher_task
    logger.info("Uploads watcher task started")
    
    logger.info("ChatBot application startup complete")
    
    yield
    
    logger.info("Shutting down ChatBot application...")
    
    task = getattr(app.state, '_uploads_watcher_task', None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("Uploads watcher task stopped")
        
    logger.info("ChatBot application shutdown complete")
