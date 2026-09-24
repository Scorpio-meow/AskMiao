import json
import logging
from typing import Callable, Dict, List

from sqlalchemy.orm import Session

from ..types import Document

logger = logging.getLogger(__name__)


class ChunkStore:
    """片段的權威儲存（資料庫 rag_chunks 表）；FAISS 與 BM25 皆以此處的 id 為鍵"""

    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory

    @staticmethod
    def _to_document(row) -> Document:
        metadata = json.loads(row.chunk_metadata)
        metadata["chunk_id"] = row.id
        return Document(page_content=row.content, metadata=metadata)

    def load_all(self) -> Dict[int, Document]:
        from app.models import RagChunk
        with self.session_factory() as session:
            rows = session.query(RagChunk).order_by(RagChunk.id).all()
            return {row.id: self._to_document(row) for row in rows}

    def insert(self, session: Session, chunks: List[Document]) -> List[int]:
        """寫入片段並 flush 取得 id（不 commit，由呼叫端與索引更新一起提交）"""
        from app.models import RagChunk
        rows = []
        for chunk in chunks:
            document_id = chunk.metadata.get("document_id")
            if document_id is None:
                raise ValueError("片段缺少 document_id，無法寫入 rag_chunks")
            rows.append(RagChunk(
                document_id=document_id,
                chunk_index=chunk.metadata["chunk_index"],
                content=chunk.page_content,
                chunk_metadata=json.dumps(chunk.metadata, ensure_ascii=False, default=str),
            ))
        session.add_all(rows)
        session.flush()
        ids = [row.id for row in rows]
        for chunk, chunk_id in zip(chunks, ids):
            chunk.metadata["chunk_id"] = chunk_id
        return ids

    def delete_ids(self, chunk_ids: List[int]) -> None:
        from app.models import RagChunk
        if not chunk_ids:
            return
        with self.session_factory() as session:
            session.query(RagChunk).filter(RagChunk.id.in_(chunk_ids)).delete(synchronize_session=False)
            session.commit()

    def delete_by_document(self, document_id: int) -> None:
        from app.models import RagChunk
        with self.session_factory() as session:
            session.query(RagChunk).filter(RagChunk.document_id == document_id).delete(synchronize_session=False)
            session.commit()

    def delete_all(self) -> None:
        from app.models import RagChunk
        with self.session_factory() as session:
            session.query(RagChunk).delete(synchronize_session=False)
            session.commit()

    def delete_orphans(self) -> int:
        """刪除所屬文件已不存在的片段（例如 SQLite 未啟用外鍵、或文件在索引之外被刪除）"""
        from app.models import RagChunk, Document as DbDocument
        with self.session_factory() as session:
            existing_ids = session.query(DbDocument.id)
            removed = (
                session.query(RagChunk)
                .filter(~RagChunk.document_id.in_(existing_ids))
                .delete(synchronize_session=False)
            )
            session.commit()
        if removed:
            logger.warning(f"已刪除 {removed} 個所屬文件不存在的孤立片段")
        return removed
