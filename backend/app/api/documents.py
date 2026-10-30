from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models import Document as DBDocument, RagChunk
from app.core.rag_manager import get_rag_system
from app.services.document_removal import remove_document
from app.core.user_context import get_current_user_id
from app.core.jwt_auth import get_current_admin_user
from app.core.limits import ADMIN_UPLOAD_EXTRACTION_LIMITS, MAX_FILENAME_BYTES, MAX_FILES_PER_UPLOAD
from app.rag.tools import invalidate_knowledge_base_description
from app.services.document_processor import DocumentProcessor, DocumentRejected
from app.services.structured_data import ExtractionResult, record_chunks
from pydantic import BaseModel
import re
import asyncio
from langchain_core.documents import Document as LangChainDocument
import os
from typing import List, Tuple
import logging
from datetime import datetime
from app.core.config import settings
logger = logging.getLogger(__name__)
router = APIRouter()
MAX_FILE_SIZE_MB = settings.MAX_FILE_SIZE_MB
UPLOAD_DIR = settings.UPLOAD_DIR
ALLOWED_EXTENSIONS = DocumentProcessor.SUPPORTED_EXTENSIONS
# 逐行判斷 Q／A 開頭；舊的跨行 DOTALL 正規式遇到大量沒有對應 A： 的 Q： 會呈超線性回溯
Q_LINE_PATTERN = re.compile(r"\s*[QＱ]\s*[：:]\s*(.*)")
A_LINE_PATTERN = re.compile(r"\s*[AＡ]\s*[：:]\s*(.*)")
def validate_filename(filename: str) -> str:
    dangerous_chars = ['/', '\\', '..', '<', '>', ':', '"', '|', '?', '*', '\0']
    for char in dangerous_chars:
        if char in filename:
            raise ValueError(f"檔名包含不允許的字元: {char}")
    from pathlib import Path
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"不允許的檔案類型: {ext}")
    if len(filename.encode("utf-8")) > MAX_FILENAME_BYTES:
        raise ValueError("檔名過長")
    return filename.replace(" ", "_")
def split_faq(text: str):
    """把「Q：…／A：…」格式的文字切成問答對。問題延續到第一個 A： 行，答案延續到下一個 Q： 行；線性時間。
    第一個 Q： 行之前有空白以外的文字時不是 FAQ，回傳空清單"""
    pairs = []
    question = None
    answer = None

    def flush():
        if question is not None and answer is not None:
            q = "\n".join(question).strip()
            a = "\n".join(answer).strip()
            if q and a:
                pairs.append((q, a))

    for line in text.splitlines():
        q_match = Q_LINE_PATTERN.match(line)
        if q_match and (question is None or answer is not None):
            flush()
            question = [q_match.group(1)]
            answer = None
            continue
        if question is None:
            if line.strip():
                return []
            continue
        if answer is None:
            a_match = A_LINE_PATTERN.match(line)
            if a_match:
                answer = [a_match.group(1)]
            else:
                question.append(line)
        else:
            answer.append(line)
    flush()
    return pairs
def process_document_for_rag(
    extraction: ExtractionResult, metadata: dict, rag_system
) -> Tuple[List[LangChainDocument], int, int]:
    if extraction.records:
        langchain_docs = [
            LangChainDocument(page_content=text, metadata={**metadata, **record_metadata})
            for record in extraction.records
            for text, record_metadata in record_chunks(record, rag_system.chunk_size)
        ]
        logger.info(f"檢測到 {len(extraction.records)} 筆結構化記錄，切成 {len(langchain_docs)} 個片段")
        return langchain_docs, 0, len(extraction.records)
    content = extraction.text
    qa_pairs = []
    if not extraction.structured_format:
        try:
            qa_pairs = split_faq(content)
        except Exception:
            qa_pairs = []
    if qa_pairs:
        langchain_docs = []
        for i, (q, a) in enumerate(qa_pairs):
            chunk_content = f"Q：{q}\nA：{a}"
            qa_metadata = {
                **metadata,
                "qa_index": i,
                "question": q[:2000],
                "preserve_whole": len(chunk_content) <= rag_system.chunk_size
            }
            langchain_docs.append(LangChainDocument(
                page_content=chunk_content,
                metadata=qa_metadata
            ))
        logger.info(f"檢測到 {len(qa_pairs)} 個 Q&A 對，不超過切塊長度者作為完整塊處理")
        return langchain_docs, len(qa_pairs), 0
    langchain_docs = [LangChainDocument(
        page_content=content,
        metadata=metadata
    )]
    return langchain_docs, 0, 0
async def reextract_or_stored(doc, missing_source_files: List[str]) -> ExtractionResult:
    file_path = os.path.join(UPLOAD_DIR, doc.filename)
    if not os.path.exists(file_path):
        missing_source_files.append(doc.filename)
        return DocumentProcessor.stored_text_extraction(doc.filename, doc.content)
    try:
        extraction = await asyncio.to_thread(
            DocumentProcessor.extract_document, file_path, doc.file_type or "text/plain", ADMIN_UPLOAD_EXTRACTION_LIMITS
        )
    except Exception as e:
        logger.warning(f"重新提取檔案 {doc.filename} 失敗，使用資料庫快取: {e}")
        return DocumentProcessor.stored_text_extraction(doc.filename, doc.content)
    if not extraction.text or not extraction.text.strip():
        return DocumentProcessor.stored_text_extraction(doc.filename, doc.content)
    doc.content = extraction.text.strip()
    return extraction
async def index_unprocessed_documents(db: Session) -> None:
    documents = (
        db.query(DBDocument)
        .filter(DBDocument.is_processed.isnot(True), ~DBDocument.id.in_(db.query(RagChunk.document_id)))
        .all()
    )
    if not documents:
        return
    rag_system = get_rag_system()
    missing_source_files = []
    for doc in documents:
        try:
            extraction = await reextract_or_stored(doc, missing_source_files)
            base_metadata = {
                "source": doc.filename,
                "document_id": doc.id,
                "uploaded_by": doc.uploaded_by,
                "content_type": doc.file_type,
                "original_filename": doc.filename
            }
            langchain_docs, _, _ = await asyncio.to_thread(
                process_document_for_rag,
                extraction,
                base_metadata,
                rag_system
            )
            added_chunks = await asyncio.to_thread(rag_system.add_documents, langchain_docs)
            doc.is_processed = True
            db.commit()
            logger.warning(f"文件 {doc.id} ({doc.filename}) 上傳時未完成索引，已補建 {added_chunks} 個分塊")
        except Exception:
            db.rollback()
            logger.exception(f"補建文件 {doc.id} ({doc.filename}) 的索引失敗")
    if missing_source_files:
        logger.warning(f"以下文件的原始檔已遺失，改以資料庫內容補建索引，請重新上傳: {missing_source_files}")
@router.post("/upload")
async def upload_document(
    file: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    current_user: dict = Depends(get_current_admin_user)
):
    if not file or len(file) == 0:
        raise HTTPException(status_code=400, detail="請上傳至少一個文件")
    if len(file) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=400, 
            detail=f"單次最多只能上傳 {MAX_FILES_PER_UPLOAD} 個檔案"
        )
    upload_dir = UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    results = []
    for up in file:
        file_path = None
        stored_document = None
        try:
            try:
                safe_filename = validate_filename(up.filename or "")
            except ValueError as e:
                logger.warning(f"檔名驗證失敗: {up.filename} - {str(e)}")
                results.append({
                    "filename": up.filename,
                    "status": "failed",
                    "detail": "檔名驗證失敗: 無效的檔名或不允許的副檔名",
                    "http_status": 400
                })
                continue
            if not DocumentProcessor.validate_file_type(up.content_type, up.filename):
                results.append({
                    "filename": up.filename,
                    "status": "failed",
                    "detail": f"不支援的文件類型: {up.content_type}",
                    "http_status": 400
                })
                continue
            max_size = MAX_FILE_SIZE_MB * 1024 * 1024
            base_name, ext = os.path.splitext(safe_filename)
            file_path = os.path.join(upload_dir, safe_filename)
            counter = 1
            while os.path.exists(file_path) or db.query(DBDocument.id).filter(DBDocument.filename == safe_filename).first():
                suffix = f"_{counter}{ext}"
                kept_bytes = MAX_FILENAME_BYTES - len(suffix.encode("utf-8"))
                safe_filename = base_name.encode("utf-8")[:kept_bytes].decode("utf-8", "ignore") + suffix
                file_path = os.path.join(upload_dir, safe_filename)
                counter += 1
            bytes_written = 0
            with open(file_path, "wb") as buffer:
                while True:
                    chunk = await up.read(1024 * 1024)
                    if not chunk:
                        break
                    buffer.write(chunk)
                    bytes_written += len(chunk)
                    if bytes_written > max_size:
                        buffer.close()
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        results.append({
                            "filename": up.filename,
                            "status": "failed",
                            "detail": f"文件大小不能超過 {MAX_FILE_SIZE_MB}MB",
                            "http_status": 400
                        })
                        break
            if bytes_written > max_size:
                continue
            file_hash = DocumentProcessor.calculate_file_hash(file_path)
            logger.info(f"Uploaded file hash: {file_hash}")
            try:
                extraction = await asyncio.to_thread(
                    DocumentProcessor.extract_document, file_path, up.content_type, ADMIN_UPLOAD_EXTRACTION_LIMITS
                )
                content = extraction.text
            except ValueError as ve:
                if os.path.exists(file_path):
                    os.remove(file_path)
                logger.warning("File extraction rejected for %s: %s", up.filename, str(ve))
                results.append({
                    "filename": safe_filename,
                    "status": "failed",
                    "detail": str(ve) if isinstance(ve, DocumentRejected) else "安全驗證失敗: 上傳的檔案未通過安全檢查",
                    "http_status": 400
                })
                continue
            except Exception as e:
                if os.path.exists(file_path):
                    os.remove(file_path)
                logger.exception("File processing error for %s", up.filename)
                results.append({
                    "filename": safe_filename,
                    "status": "failed",
                    "detail": "檔案處理錯誤: 內部錯誤，請聯繫系統管理員",
                    "http_status": 500
                })
                continue
            if not content or not content.strip():
                if os.path.exists(file_path):
                    os.remove(file_path)
                results.append({
                    "filename": safe_filename,
                    "status": "failed",
                    "detail": "無法從文件中擷取文字內容",
                    "http_status": 400
                })
                continue
            content = content.strip()
            existing = await asyncio.to_thread(
                lambda: db.query(DBDocument.id).filter(DBDocument.content == content).first()
            )
            if existing:
                logger.info(f"Duplicate upload detected for file {up.filename}; existing document id={existing.id}")
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception:
                    pass
                results.append({
                    "filename": safe_filename,
                    "status": "duplicate",
                    "detail": "內容已存在",
                    "existing_document_id": existing.id,
                    "http_status": 409
                })
                continue
            doc_desc = await DocumentProcessor.generate_document_summary_async(
                safe_filename, content, up.content_type or "", extraction=extraction
            )
            document = DBDocument(
                filename=safe_filename,
                content=content,
                file_type=up.content_type,
                description=doc_desc,
                uploaded_by=user_id
            )
            db.add(document)
            db.commit()
            stored_document = document
            invalidate_knowledge_base_description()
            db.refresh(document)
            rag_system = get_rag_system()
            base_metadata = {
                "source": safe_filename,
                "document_id": document.id,
                "uploaded_by": user_id,
                "content_type": up.content_type,
                "original_filename": up.filename
            }
            logger.info(f"正在對文件 {safe_filename} ({len(content)} 字元) 進行分塊處理...")
            langchain_docs, qa_count, record_count = await asyncio.to_thread(
                process_document_for_rag, extraction, base_metadata, rag_system
            )
            logger.info(f"正在將文件 {safe_filename} 提交至 RAG 引擎進行分塊與向量化...")
            added_chunks = await asyncio.to_thread(rag_system.add_documents, langchain_docs)
            document.is_processed = True
            db.commit()
            invalidate_knowledge_base_description()
            logger.info(f"文件 {safe_filename} 成功入庫並完成向量索引 (共 {added_chunks} 塊)")
            results.append({
                "filename": safe_filename,
                "status": "success",
                "document_id": document.id,
                "content_length": len(content),
                "content_type": up.content_type,
                "qa_detected": qa_count > 0,
                "qa_pairs": qa_count,
                "record_count": record_count,
                "warning": extraction.warning,
                "http_status": 201
            })
        except Exception as e:
            logger.exception("處理文件 %s 失敗", up.filename)
            try:
                db.rollback()
                if stored_document is not None:
                    await remove_document(db, stored_document)
            except Exception:
                logger.exception("清除上傳失敗的文件 %s 失敗", up.filename)
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass
            results.append({
                "filename": up.filename,
                "status": "failed",
                "detail": "内部錯誤，處理失敗。請聯繫系統管理員。",
                "http_status": 500
            })
    return {"results": results}
# 文件清單只送畫面需要的欄位：全文可能很大，清單頁與管理後台都用不到
DOCUMENT_LIST_COLUMNS = (
    DBDocument.id,
    DBDocument.filename,
    DBDocument.file_type,
    DBDocument.description,
    DBDocument.uploaded_by,
    DBDocument.created_at,
    DBDocument.is_processed,
)
@router.get("/")
def get_documents(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    return [row._asdict() for row in db.query(*DOCUMENT_LIST_COLUMNS).all()]
class DocumentSummaryUpdate(BaseModel):
    description: str
@router.post("/{document_id}/regenerate-summary")
async def regenerate_document_summary(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    """手動或一鍵重新生成該文件的 AI 智能大綱與摘要"""
    document = db.query(DBDocument).filter(DBDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="文件不存在")
    new_desc = await DocumentProcessor.generate_document_summary_async(
        document.filename, document.content, document.file_type or "text/plain"
    )
    document.description = new_desc
    db.add(document)
    db.commit()
    invalidate_knowledge_base_description()
    db.refresh(document)
    return {
        "message": "文件大綱與摘要重新生成成功",
        "document_id": document.id,
        "description": new_desc
    }
@router.put("/{document_id}/summary")
async def update_document_summary(
    document_id: int,
    payload: DocumentSummaryUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    """手動編輯儲存該文件的大綱描述"""
    document = db.query(DBDocument).filter(DBDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="文件不存在")
    document.description = payload.description.strip()
    db.add(document)
    db.commit()
    invalidate_knowledge_base_description()
    db.refresh(document)
    return {
        "message": "文件大綱更新成功",
        "document_id": document.id,
        "description": document.description
    }
@router.delete("/{document_id}")
async def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    document = db.query(DBDocument).filter(DBDocument.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="文件不存在")
    await remove_document(db, document)
    return {"message": "文件刪除成功"}
# 重建逐份移除並寫回文件的片段，同時跑兩次會讓同一份文件的片段寫進兩份
_rebuild_lock = asyncio.Lock()
@router.post("/rebuild-index")
async def rebuild_index(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin_user)
):
    if _rebuild_lock.locked():
        raise HTTPException(status_code=409, detail="索引重建正在進行中，請等待完成後再試")
    async with _rebuild_lock:
        return await _rebuild_all_documents(db, current_user)
async def _rebuild_all_documents(db: Session, current_user: dict):
    try:
        logger.info(f"管理員 {current_user.get('username', 'unknown')} 觸發完整索引重建（含重新分塊與補齊摘要）")
        rag_system = get_rag_system()
        logger.info("從數據庫重新載入文檔...")
        documents_from_db = db.query(DBDocument).all()
        if not documents_from_db:
            logger.warning("數據庫中沒有文檔")
            return {
                "message": "索引重建完成（沒有文件）",
                "document_count": 0,
                "chunk_count": 0,
                "qa_pairs_detected": 0,
                "records_detected": 0,
                "missing_source_files": [],
                "failed_documents": [],
                "timestamp": datetime.now().isoformat()
            }
        logger.info(f"用新配置重新處理 {len(documents_from_db)} 個文檔（chunk_size={rag_system.chunk_size}, chunk_overlap={rag_system.chunk_overlap}）...")
        total_chunks = 0
        total_qa_pairs = 0
        total_records = 0
        missing_source_files = []
        failed_documents = []
        for doc in documents_from_db:
            try:
                extraction = await reextract_or_stored(doc, missing_source_files)
                # 只替沒有摘要的文件產生摘要：管理員手動修訂過的摘要不能被覆蓋
                if not (doc.description or "").strip():
                    doc.description = await DocumentProcessor.generate_document_summary_async(
                        doc.filename, extraction.text, doc.file_type or "text/plain", extraction=extraction
                    )
                db.add(doc)
                db.commit()
                invalidate_knowledge_base_description()
                base_metadata = {
                    "source": doc.filename,
                    "document_id": doc.id,
                    "uploaded_by": doc.uploaded_by,
                    "content_type": doc.file_type,
                    "original_filename": doc.filename
                }
                langchain_docs, qa_count, record_count = await asyncio.to_thread(
                    process_document_for_rag, extraction, base_metadata, rag_system
                )
                await asyncio.to_thread(rag_system.remove_document_by_id, doc.id)
                chunks_added = await asyncio.to_thread(rag_system.add_documents, langchain_docs)

                total_chunks += chunks_added or 0
                total_qa_pairs += qa_count
                total_records += record_count
                logger.info(
                    f"處理文檔 {doc.id} ({doc.filename}): {chunks_added} 個分塊（{qa_count} 個 Q&A 對、{record_count} 筆記錄）"
                )
            except Exception as e:
                logger.exception(f"處理文檔 {doc.id} ({doc.filename}) 失敗")
                failed_documents.append({"document_id": doc.id, "filename": doc.filename})
                continue
        doc_count = len(documents_from_db)
        vector_count = rag_system.index.ntotal
        logger.info(
            f"索引重建完成: {doc_count} 個文檔 -> {vector_count} 個向量塊 "
            f"(含 {total_qa_pairs} 個 Q&A 對、{total_records} 筆結構化記錄)"
        )
        if missing_source_files:
            logger.warning(f"以下文件的原始檔已遺失，改以資料庫內容重建，請重新上傳: {missing_source_files}")
        if failed_documents:
            logger.warning(f"以下文件重建索引失敗: {failed_documents}")
        return {
            "message": (
                f"索引重建完成，但有 {len(failed_documents)} 份文件處理失敗"
                if failed_documents
                else "索引重建成功（已用新配置重新分塊，並替缺少摘要的文件生成 AI 智能大綱）"
            ),
            "document_count": doc_count,
            "chunk_count": vector_count,
            "qa_pairs_detected": total_qa_pairs,
            "records_detected": total_records,
            "missing_source_files": missing_source_files,
            "failed_documents": failed_documents,
            "chunk_size": rag_system.chunk_size,
            "chunk_overlap": rag_system.chunk_overlap,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.exception("索引重建失敗")
        raise HTTPException(status_code=500, detail="索引重建失敗: 內部錯誤，請聯繫系統管理員")
