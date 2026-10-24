import os
import sys
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)
from app.models.database import SessionLocal
from app.rag.tools import invalidate_knowledge_base_description
from app.models import Document as DBDocument
from app.services.document_processor import DocumentProcessor
from app.core.rag_manager import get_rag_system
from app.api.documents import process_document_for_rag, reextract_or_stored
import asyncio
async def reprocess_all():
    db = SessionLocal()
    rag_system = get_rag_system()

    print("=== 開始重新處理現有文件庫 ===")
    docs = db.query(DBDocument).all()
    if not docs:
        print("資料庫中無任何文件記錄。")
        db.close()
        return
    print("清空現有 RAG 片段、向量與 BM25 索引...")
    rag_system.clear_indices()
    total_chunks = 0
    total_records = 0
    missing_source_files = []
    for doc in docs:
        print(f"\n--- 處理文檔: {doc.filename} (ID: {doc.id}) ---")
        extraction = await reextract_or_stored(doc, missing_source_files)
        if extraction.warning:
            print(f"注意: {extraction.warning}")
        content = extraction.text

        summary = await DocumentProcessor.generate_document_summary_async(
            doc.filename, content, doc.file_type or "text/plain", extraction=extraction
        )
        doc.description = summary
        db.add(doc)
        db.commit()
        invalidate_knowledge_base_description()
        print(f"新 AI 大綱摘要: {summary}")
        print(f"提取字數: {len(content)} 字元")
        base_metadata = {
            "source": doc.filename,
            "document_id": doc.id,
            "uploaded_by": doc.uploaded_by,
            "content_type": doc.file_type,
            "original_filename": doc.filename
        }
        langchain_docs, qa_count, record_count = process_document_for_rag(extraction, base_metadata, rag_system)
        chunks_added = rag_system.add_documents(langchain_docs)
        total_chunks += (chunks_added or 0)
        total_records += record_count
        print(f"已建立向量分塊: {chunks_added} 塊（{qa_count} 個 Q&A 對、{record_count} 筆記錄）")
    db.close()
    print(f"\n=== 重建完成！共處理 {len(docs)} 份文檔，建立 {total_chunks} 個向量塊、{total_records} 筆結構化記錄 ===")
    if missing_source_files:
        print(f"以下文件的原始檔已遺失，改以資料庫內容重建，請重新上傳: {', '.join(missing_source_files)}")
if __name__ == "__main__":
    asyncio.run(reprocess_all())
