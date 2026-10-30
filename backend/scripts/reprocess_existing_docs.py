import os
import sys
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)
from app.models.database import SessionLocal
from app.api.documents import _rebuild_all_documents
import asyncio
async def reprocess_all():
    db = SessionLocal()
    print("=== 開始重新處理現有文件庫 ===")
    try:
        result = await _rebuild_all_documents(db, {"username": os.path.basename(__file__)})
    finally:
        db.close()
    print(result["message"])
    print(f"共處理 {result['document_count']} 份文檔，建立 {result['chunk_count']} 個向量塊、{result['records_detected']} 筆結構化記錄")
    if result["missing_source_files"]:
        print(f"以下文件的原始檔已遺失，改以資料庫內容重建，請重新上傳: {', '.join(result['missing_source_files'])}")
    if result["failed_documents"]:
        print(f"以下文件重建失敗: {', '.join(item['filename'] for item in result['failed_documents'])}")
if __name__ == "__main__":
    asyncio.run(reprocess_all())
