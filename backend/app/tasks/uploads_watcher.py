import asyncio
import os
import logging
from typing import Callable, Set
from sqlalchemy.orm import Session
from app.models import Document
from app.models.database import SessionLocal
from app.core.config import settings

logger = logging.getLogger(__name__)


def check_missing_uploads(session_factory: Callable[[], Session], upload_dir: str, warned_ids: Set[int]) -> None:
    """檢查上傳檔是否還在。文件內容已存於資料庫，檔案遺失只記一次警告，不刪除索引或資料庫紀錄"""
    with session_factory() as db:
        documents = db.query(Document.id, Document.filename).all()
    current_ids = set()
    for document_id, filename in documents:
        current_ids.add(document_id)
        if filename and os.path.exists(os.path.join(upload_dir, filename)):
            warned_ids.discard(document_id)
        elif document_id not in warned_ids:
            warned_ids.add(document_id)
            logger.warning(
                f"文件 id={document_id}（{filename}）的上傳檔不在 {upload_dir}；"
                "知識庫繼續使用資料庫中的內容，索引與資料庫紀錄都不會變動"
            )
    warned_ids.intersection_update(current_ids)


async def watch_missing_uploads(interval_seconds: int) -> None:
    warned_ids: Set[int] = set()
    while True:
        try:
            await asyncio.to_thread(check_missing_uploads, SessionLocal, settings.UPLOAD_DIR, warned_ids)
        except Exception as e:
            logger.error(f"Error in uploads watcher: {e}")
        await asyncio.sleep(interval_seconds)
