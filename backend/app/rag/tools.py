import asyncio
import json
import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from pathlib import PurePosixPath
from urllib.parse import urlparse
import httpx
from app.core.config import settings
from app.core.domain_profile import domain_profile
from app.core.error_response import format_ssrf_rejection, log_and_get_error_id
from app.core.html_text import extract_text_and_title
from app.core.limits import MAX_KB_CATALOG_CHARS, MAX_MCP_CATALOG_CHARS, MAX_SKILL_CATALOG_CHARS, MAX_TEXT_CLEANUP_CHARS
from app.rag.retrievers.hybrid import matches_target_document
from app.services import agent_skills
from app.services.structured_data import merge_record_parts
from app.services.structured_data.render import RENDERED_HEADER_PATTERN
logger = logging.getLogger(__name__)
WEB_TOOL_NAMES = ("web_search", "web_fetch")
SKILL_TOOL_NAMES = ("activate_skill", "read_skill_resource")
MCP_CATALOG_TOOL_NAMES = ("read_mcp_resource", "get_mcp_prompt")
SKILL_SCRIPT_TOOL_NAME = "run_skill_script"
BUILTIN_TOOL_NAMES = ("search_knowledge_base", "filter_and_count_records") + WEB_TOOL_NAMES + SKILL_TOOL_NAMES
def is_web_fetch_domain_allowed(url: str) -> bool:
    """WEB_FETCH_ALLOWED_DOMAINS 為 * 時不限制；否則主機須為清單中的網域或其子網域"""
    allowed = settings.web_fetch_allowed_domains
    if allowed == ["*"]:
        return True
    host = (urlparse(url).hostname or "").rstrip(".")
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed)
# 知識庫工具描述的快取：每次聊天與工具清單都會用到，重算需要讀出所有文件
KB_DESCRIPTION_CACHE_SECONDS = 60.0
_kb_description_lock = threading.Lock()
_kb_description_cache: Optional[Tuple[float, Tuple[str, List[str]]]] = None


def _url_host(url: str) -> str:
    """只取主機與連接埠，不帶路徑、查詢字串或帳號資訊"""
    parsed = urlparse(url)
    if parsed.hostname is None:
        return ""
    return f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname


def _without_label_and_link_fields(content: str, label: Optional[str], links: List[str]) -> str:
    duplicates = set(links) | ({label} if label else set())
    if not duplicates:
        return content
    lines = content.split("\n")
    if lines and RENDERED_HEADER_PATTERN.match(lines[0]):
        lines = lines[1:]
    return "\n".join(line for line in lines if line.partition(": ")[2].strip() not in duplicates)


def invalidate_knowledge_base_description() -> None:
    global _kb_description_cache
    with _kb_description_lock:
        _kb_description_cache = None


# filter_and_count_records 的參數上限：date_range 由模型提供，展開出的日期字串數決定掃描成本
MAX_DATE_RANGE_CHARS = 200
MAX_TARGET_DATES = 93
MAX_FILTER_RECORDS = 50


def extract_html_text(html_content: str) -> Tuple[str, str]:
    """回傳 (title, 內文文字)。以線性掃描取代回溯正規式：未閉合的標籤會讓那些正規式呈二次時間"""
    title, text, _ = extract_text_and_title((html_content or "")[:MAX_TEXT_CLEANUP_CHARS])
    return title, text


def clean_html(html_content: str) -> str:
    """清理 HTML 標籤並擷取核心文字內容"""
    return extract_html_text(html_content)[1][:4000]


def _expand_target_dates(date_range: str) -> List[str]:
    target_dates: List[str] = []
    for m in re.finditer(r'(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?', date_range):
        y = m.group(1)
        mth = int(m.group(2))
        d = int(m.group(3)) if m.group(3) else None
        if d is not None:
            target_dates.extend([f"{y}-{mth:02d}-{d:02d}", f"{y}年{mth}月{d}日", f"{y}年{mth:02d}月{d:02d}日"])
        else:
            target_dates.extend([f"{y}-{mth:02d}", f"{y}年{mth}月", f"{y}年{mth:02d}月"])
    for m in re.finditer(r'(\d{4})年\s*(\d{1,2})月(?:\s*(\d{1,2})日)?', date_range):
        y = m.group(1)
        mth = int(m.group(2))
        d = int(m.group(3)) if m.group(3) else None
        if d is not None:
            target_dates.extend([f"{y}-{mth:02d}-{d:02d}", f"{y}年{mth}月{d}日", f"{y}年{mth:02d}月{d:02d}日"])
        else:
            target_dates.extend([f"{y}-{mth:02d}", f"{y}年{mth}月", f"{y}年{mth:02d}月"])
    return list(dict.fromkeys(target_dates))
class ResearchToolRegistry:
    """研究工具註冊中心：提供知識庫檢索、聯網搜尋與網頁深入閱讀工具"""
    def __init__(self, retriever=None):
        self.retriever = retriever
    def set_retriever(self, retriever):
        self.retriever = retriever
    async def search_knowledge_base(self, query: str, top_k: int = 3, target_document: Optional[str] = None) -> Dict[str, Any]:
        """檢索本機與企業內部知識庫（向量與 BM25 以 RRF 融合後重排，只回傳通過相關性門檻的片段，可選限定特定文件）"""
        if not self.retriever:
            return {"error": "知識庫檢索器尚未初始化", "documents": []}

        try:
            results = await asyncio.to_thread(self.retriever.smart_search, query, target_document)
            if not results:
                message = f"指定文件《{target_document}》中查無相關資料" if target_document else "知識庫中查無相關資料"
                return {
                    "query": query,
                    "target_document": target_document,
                    "total_found": 0,
                    "returned": 0,
                    "documents": [],
                    "message": message
                }

            # 精確比對到網址、貼文 ID、日期的片段全部回傳，其餘依 top_k
            effective_k = max(top_k, sum(1 for r in results if r.pinned))
            docs_info = []
            for result in results[:effective_k]:
                doc = result.document
                docs_info.append({
                    "chunk_id": doc.metadata["chunk_id"],
                    "source": doc.metadata.get("source", "未知文件"),
                    "chunk_index": doc.metadata.get("chunk_index", 0),
                    "score": round(result.score, 4),
                    "label": doc.metadata.get("label"),
                    "links": doc.metadata.get("links", []),
                    "content": doc.page_content.strip()
                })

            return {
                "query": query,
                "target_document": target_document,
                "total_found": len(results),
                "returned": len(docs_info),
                "documents": docs_info
            }
        except Exception as e:
            error_id = log_and_get_error_id(logger, "search_knowledge_base 執行失敗", e)
            return {"error": f"檢索知識庫時發生錯誤（錯誤代碼：{error_id}）", "documents": []}
    async def filter_and_count_records(
        self,
        date_range: Optional[str] = None,
        author: Optional[str] = None,
        keyword: Optional[str] = None,
        target_document: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        精準統計與條件篩選知識庫中的結構化記錄/貼文/文件。
        計算特定發布月份/日期（如 2026年8月、2025-10-22）、特定作者、關鍵字或特定文件的總筆數（精確 count），
        並回傳符合條件的記錄清單。
        """
        if not self.retriever or not hasattr(self.retriever, "vector_store") or not self.retriever.vector_store.documents:
            return {"error": "知識庫尚未載入", "total_count": 0, "records": []}
        if date_range and len(date_range) > MAX_DATE_RANGE_CHARS:
            return {"error": f"date_range 不可超過 {MAX_DATE_RANGE_CHARS} 個字元", "total_count": 0, "records": []}
        try:
            limit = max(1, min(int(limit), MAX_FILTER_RECORDS))
        except (TypeError, ValueError):
            limit = MAX_FILTER_RECORDS
        try:
            # 逐筆掃描整個語料，移到執行緒以免阻塞事件迴圈
            return await asyncio.to_thread(
                self._filter_records_sync, date_range, author, keyword, target_document, limit
            )
        except Exception as e:
            error_id = log_and_get_error_id(logger, "filter_and_count_records 執行失敗", e)
            return {"error": f"統計篩選時發生錯誤（錯誤代碼：{error_id}）", "total_count": 0, "records": []}
    def _filter_records_sync(
        self,
        date_range: Optional[str],
        author: Optional[str],
        keyword: Optional[str],
        target_document: Optional[str],
        limit: int
    ) -> Dict[str, Any]:
        docs = self.retriever.vector_store.documents
        target_dates = _expand_target_dates(date_range) if date_range else []
        keywords = [k.strip() for k in re.split(r"[,，、]", (keyword or "").lower()) if k.strip()]
        if len(target_dates) > MAX_TARGET_DATES:
            return {"error": "date_range 包含的日期過多，請縮小範圍", "total_count": 0, "records": []}
        # 所有日期合併成一個正規式，每筆記錄只掃描一次
        dates_alternation = "|".join(re.escape(td) for td in target_dates)
        field_patterns: Dict[str, "re.Pattern[str]"] = {}
        matched_records = []
        record_parts: Dict[Tuple[Any, ...], List[Any]] = {}
        for doc in docs:
            if target_document and not matches_target_document(doc, target_document):
                continue
            record_index = doc.metadata.get("record_index")
            if record_index is None:
                key = ("chunk", doc.metadata["chunk_id"])
            else:
                key = ("record", doc.metadata.get("document_id"), record_index)
            record_parts.setdefault(key, []).append(doc)
        for parts in record_parts.values():
            parts.sort(key=lambda part: part.metadata.get("part", 1))
            first = parts[0]
            content = first.page_content if len(parts) == 1 else merge_record_parts([part.page_content for part in parts])
            c_lower = content.lower()

            if target_dates:
                # 記錄有發布日期欄位時只比對該欄位，避免內文提到的其他日期被算進去
                date_fields = tuple(f for f in domain_profile.record_date_fields if f"{f}:" in content)
                if date_fields:
                    pattern = field_patterns.get(date_fields)
                    if pattern is None:
                        fields_alternation = "|".join(re.escape(field) for field in date_fields)
                        pattern = re.compile(rf'(?:{fields_alternation}):\s*(?:{dates_alternation})')
                        field_patterns[date_fields] = pattern
                    has_date = pattern.search(content) is not None
                else:
                    has_date = any(td in content for td in target_dates)
                if not has_date:
                    continue

            if author:
                auth_clean = author.lstrip("@").lower()
                if auth_clean not in c_lower:
                    continue

            if keywords and not any(k in c_lower for k in keywords):
                continue
            label = first.metadata.get("label")
            links = first.metadata.get("links", [])
            matched_records.append({
                "chunk_id": first.metadata["chunk_id"],
                "source": first.metadata.get("source", "未知文件"),
                "record_index": first.metadata.get("record_index"),
                "label": label,
                "links": links,
                "content": _without_label_and_link_fields(content, label, links).strip()
            })
        total_count = len(matched_records)
        returned_records = matched_records[:limit]
        return {
            "total_count": total_count,
            "filter_criteria": {
                "date_range": date_range,
                "author": author,
                "keyword": keyword,
                "target_document": target_document
            },
            "returned_count": len(returned_records),
            "summary": f"在知識庫中精確統計到 {total_count} 則符合條件的記錄/貼文（本次回傳前 {len(returned_records)} 則）。",
            "records": returned_records
        }
    async def web_search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """執行聯網搜尋以獲取外部即時資訊（優先調用 Ollama 官方搜尋 API，失敗時自動調用 DuckDuckGo 備援）"""
        ollama_key = settings.OLLAMA_API_KEY or ''
        

        if ollama_key:
            try:
                search_endpoint = settings.OLLAMA_SEARCH_ENDPOINT
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        search_endpoint,
                        headers={"Authorization": f"Bearer {ollama_key}"},
                        json={"query": query, "max_results": max_results}
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        results = data.get("results", [])
                        return {
                            "query": query,
                            "engine": "ollama",
                            "count": len(results),
                            "results": results
                        }
                    else:
                        logger.warning(f"Ollama Web Search API 返回狀態碼 {resp.status_code}，切換至備援引擎")
            except Exception as e:
                logger.warning(f"Ollama Web Search 失敗: {e}，切換至備援引擎")

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            ddg_endpoint = settings.DUCKDUCKGO_SEARCH_ENDPOINT
            async with httpx.AsyncClient(headers=headers, timeout=12.0, follow_redirects=True) as client:
                resp = await client.get(
                    ddg_endpoint,
                    params={"q": query}
                )
                if resp.status_code == 200:
                    results = []

                    links = re.findall(r'<a class="result__url"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', resp.text)
                    titles = re.findall(r'<a class="result__a"[^>]*>([\s\S]*?)</a>', resp.text)
                    snippets = re.findall(r'<a class="result__snippet"[^>]*>([\s\S]*?)</a>', resp.text)
                    
                    for i in range(min(len(titles), max_results)):
                        clean_title = clean_html(titles[i]) if i < len(titles) else ""
                        raw_link = links[i][0] if i < len(links) else ""
                        clean_snippet = clean_html(snippets[i]) if i < len(snippets) else ""
                        

                        actual_url = raw_link
                        uddg_match = re.search(r'uddg=([^&]+)', raw_link)
                        if uddg_match:
                            import urllib.parse
                            actual_url = urllib.parse.unquote(uddg_match.group(1))
                        if clean_title and actual_url:
                            results.append({
                                "title": clean_title,
                                "url": actual_url,
                                "snippet": clean_snippet
                            })
                    return {
                        "query": query,
                        "engine": "duckduckgo_fallback",
                        "count": len(results),
                        "results": results
                    }
                else:
                    return {"query": query, "error": f"搜尋失敗，狀態碼: {resp.status_code}", "results": []}
        except Exception as e:
            error_id = log_and_get_error_id(logger, "DuckDuckGo 搜尋失敗", e)
            return {"query": query, "error": f"外部搜尋發生錯誤（錯誤代碼：{error_id}）", "results": []}
    async def web_fetch(self, url: str) -> Dict[str, Any]:
        """深入讀取指定網頁全文（優先使用 Ollama Web Fetch，失敗時使用具備 SSRF 防護之 HTTP 抓取並解析 HTML）"""
        from app.core.ssrf_protection import DnsPool, safe_fetch_text, validate_url_ssrf, SSRFProtectionError

        if not is_web_fetch_domain_allowed(url):
            return {"url": url, "error": "該網址的網域不在 WEB_FETCH_ALLOWED_DOMAINS 允許清單內", "content": ""}

        is_safe, error_msg, _ = await validate_url_ssrf(url, DnsPool.USER_URL)
        if not is_safe:
            # 拒絕原因可能含伺服器端 DNS 解析結果，只寫入日誌
            error_id = log_and_get_error_id(
                logger, f"web_fetch 網址被 SSRF 防護拒絕: {error_msg}", SSRFProtectionError(error_msg), logging.WARNING
            )
            return {"url": url, "error": format_ssrf_rejection(error_id), "content": ""}

        ollama_key = settings.OLLAMA_API_KEY or ''

        if ollama_key:
            try:
                fetch_endpoint = settings.OLLAMA_FETCH_ENDPOINT
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        fetch_endpoint,
                        headers={"Authorization": f"Bearer {ollama_key}"},
                        json={"url": url}
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        return {
                            "url": url,
                            "title": data.get("title", ""),
                            "content": data.get("content", "")[:3500]
                        }
            except Exception as e:
                logger.warning(f"Ollama Web Fetch 失敗: {e}，切換為直接安全連線讀取")

        try:
            raw_html = await safe_fetch_text(
                url=url,
                dns_pool=DnsPool.USER_URL,
                timeout=12.0,
                max_redirects=5,
                max_size_bytes=5 * 1024 * 1024
            )
            # HTML 解析是 CPU 密集工作，移到執行緒以免阻塞事件迴圈
            title, clean_text = await asyncio.to_thread(extract_html_text, raw_html)
            return {
                "url": url,
                "title": title or url,
                "content": clean_text[:3500]
            }
        except (SSRFProtectionError, ValueError) as e:
            error_id = log_and_get_error_id(logger, f"web_fetch 遭安全防護或格式驗證拒絕 ({url})", e)
            return {"url": url, "error": f"網頁讀取失敗：該網址遭安全防護拒絕或格式無效（錯誤代碼：{error_id}）", "content": ""}
        except Exception as e:
            error_id = log_and_get_error_id(logger, f"web_fetch 失敗 ({url})", e)
            return {"url": url, "error": f"無法存取該網址（錯誤代碼：{error_id}）", "content": ""}
    def _generate_knowledge_base_description(self) -> Tuple[str, List[str]]:
        """根據知識庫收錄的每一份文件內容結構，純動態生成互不相同且專屬之主題描述；
        結果快取 KB_DESCRIPTION_CACHE_SECONDS 秒，同時只有一個執行緒重算"""
        global _kb_description_cache
        with _kb_description_lock:
            now = time.monotonic()
            if _kb_description_cache is not None and now - _kb_description_cache[0] < KB_DESCRIPTION_CACHE_SECONDS:
                return _kb_description_cache[1]
            description = self._build_knowledge_base_description()
            _kb_description_cache = (now, description)
            return description
    def _build_knowledge_base_description(self) -> Tuple[str, List[str]]:
        from app.services.document_processor import DocumentProcessor
        doc_items = []
        try:
            from app.models.database import SessionLocal
            from app.models import Document
            db = SessionLocal()
            try:
                # 只讀需要的欄位；全文只在缺少描述、必須即時產生摘要時才載入
                rows = db.query(Document.id, Document.filename, Document.description, Document.file_type).all()
                for row in rows:
                    desc = row.description
                    if not desc:
                        content = db.query(Document.content).filter(Document.id == row.id).scalar()
                        if content:
                            desc = DocumentProcessor.generate_document_summary(row.filename, content, row.file_type or "")
                    doc_items.append((row.filename, desc or f"收錄內部文件《{row.filename}》。"))
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"從資料庫讀取文件描述失敗: {e}")

        if not doc_items and self.retriever and hasattr(self.retriever, "vector_store") and hasattr(self.retriever.vector_store, "documents"):
            seen = set()
            for d in self.retriever.vector_store.documents:
                src = d.metadata.get("source") or d.metadata.get("original_filename")
                if src and src not in seen:
                    seen.add(src)
                    desc = DocumentProcessor.generate_document_summary(src, d.page_content)
                    doc_items.append((src, desc))
        if not doc_items:
            return "檢索已上傳之內部知識庫與專業文件資料。當使用者提供特定網址連結、作者帳號或查詢內部檔案時必須優先調用。", []
        doc_descriptions = []
        filenames: List[str] = []
        catalog_chars = 0
        for idx, (filename, desc) in enumerate(doc_items, start=1):
            line = f"{idx}. 《{filename}》：{desc}"
            catalog_chars += len(line)
            if catalog_chars > MAX_KB_CATALOG_CHARS:
                doc_descriptions.append(
                    f"另有 {len(doc_items) - idx + 1} 份文件未列出，仍可直接檢索，或以 target_document 指定檔名。"
                )
                filenames = []
                break
            doc_descriptions.append(line)
            filenames.append(filename)
        catalog_text = "\n".join(doc_descriptions)
        return (
            "檢索內部知識庫。目前知識庫收錄以下各具不同主題之專屬文件庫，調用時請針對相應主題檢索：\n"
            f"{catalog_text}\n"
            "當使用者提問涉及上述任一文件的專屬領域時，必須優先調用此工具。"
        ), filenames
    def get_tool_definitions(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """回傳 OpenAI / Ollama / Azure OpenAI 相容之 Function Calling 工具規格清單（包含內部預設工具與已啟用的自訂 API Tools）"""
        kb_desc, doc_names = self._generate_knowledge_base_description()
        target_document_schema: Dict[str, Any] = {
            "type": "string",
            "description": "可選：限定只查這份文件，須與 search_knowledge_base 說明中《》內的檔名完全相同；不確定就留空查全庫。"
        }
        if doc_names:
            target_document_schema["enum"] = doc_names
        base_tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_knowledge_base",
                    "description": kb_desc,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "要檢索的關鍵字、作者帳號或特定網址；中文一律用繁體字（知識庫是繁體中文，簡體字會查不到）"
                            },
                            "target_document": target_document_schema,
                            "top_k": {
                                "type": "integer",
                                "description": "返回的最相關文件片段數量（預設 3，最大 5）",
                                "default": 3
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "filter_and_count_records",
                    "description": "精準統計與條件篩選知識庫中的結構化貼文/記錄/文件。可用於計算特定發布月份/日期（如 '2026年8月'、'2025-10-22'）、特定作者（如 '@example_user'）、特定關鍵字或特定文件的總筆數（精確 count），並可取得符合條件的完整或批次清單。當使用者詢問『總共有幾則』、『統計』、『列出某年某月所有貼文』或『某作者的全部記錄』時[必須優先調用此工具]。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date_range": {
                                "type": "string",
                                "description": "篩選發布日期或月份（如 '2026-08', '2026年8月', '2025-10-22', '2025年10月22日'）。優先匹配發布時間。"
                            },
                            "author": {
                                "type": "string",
                                "description": "篩選特定作者帳號（如 '@example_user' 或 'example_user'）"
                            },
                            "keyword": {
                                "type": "string",
                                "description": "篩選內容中包含的關鍵字"
                            },
                            "target_document": target_document_schema,
                            "limit": {
                                "type": "integer",
                                "description": "返回清單筆數上限（預設 50，最大 200）",
                                "default": 50
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "執行外部網路搜尋，獲取最新公開即時資訊、時事新聞或內部知識庫未涵蓋的外部公開資料。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜尋引擎關鍵字"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "最大搜尋結果筆數（預設 5）",
                                "default": 5
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "web_fetch",
                    "description": "深入閱讀與抓取指定公開網頁的全文內容。當 web_search 返回的摘要不足以完整回答時，可調用此工具深入閱讀特定網址。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "要讀取的完整網址（http:// 或 https://）"
                            }
                        },
                        "required": ["url"]
                    }
                }
            }
        ]
        if not settings.ENABLE_WEB_SEARCH:
            base_tools = [t for t in base_tools if t["function"]["name"] not in WEB_TOOL_NAMES]
        try:
            base_tools.extend(self._skill_tool_definitions(user_id))
        except Exception as e:
            logger.warning(f"載入 Agent Skills 失敗: {e}")

        try:
            from app.models.database import SessionLocal
            from app.models import CustomApiTool, McpServer
            from app.services.mcp_service import McpManager
            db = SessionLocal()
            custom_tools = db.query(CustomApiTool).filter(CustomApiTool.is_enabled == True).all()
            for ct in custom_tools:
                p_schema = {"type": "object", "properties": {}}
                if ct.parameters_schema:
                    try:
                        p_schema = json.loads(ct.parameters_schema)
                    except Exception:
                        pass
                
                desc = ct.description or ct.display_name or ct.name
                base_tools.append({
                    "type": "function",
                    "function": {
                        "name": ct.name,
                        "description": f"[外部自訂 API]{ct.display_name}：{desc}",
                        "parameters": p_schema
                    }
                })

            mcp_servers = db.query(McpServer).filter(McpServer.is_enabled == True).all()
            for ms in mcp_servers:
                if ms.discovered_tools:
                    try:
                        tools_list = json.loads(ms.discovered_tools)
                        for mt in tools_list:
                            fdef = McpManager.convert_mcp_tool_to_function_def(
                                server_name=ms.name,
                                server_display_name=ms.display_name,
                                mcp_tool=mt
                            )
                            base_tools.append(fdef)
                    except Exception as e:
                        logger.warning(f"解析 MCP 伺服器 {ms.name} 工具快取失敗: {e}")
            base_tools.extend(self._mcp_catalog_tool_definitions(mcp_servers))
            db.close()
        except Exception as e:
            logger.warning(f"動態載入外部工具或 MCP 失敗: {e}")
        return base_tools
    @staticmethod
    def _mcp_catalog(server, column: str) -> List[Dict[str, Any]]:
        try:
            items = json.loads(getattr(server, column) or "[]")
        except Exception:
            return []
        return items if isinstance(items, list) else []
    def _mcp_catalog_tool_definitions(self, servers: List[Any]) -> List[Dict[str, Any]]:
        definitions = []
        for tool_name, column, header, render, parameters in (
            (
                "read_mcp_resource",
                "discovered_resources",
                "讀取 MCP 伺服器提供的 resource（文件、資料等）內容，只能讀取下列清單中的 uri：\n",
                lambda r: f"- {r['uri']}｜{r.get('name') or ''}{('：' + r['description']) if r.get('description') else ''}",
                {"uri": {"type": "string", "description": "要讀取的 resource uri，必須與清單完全相同"}},
            ),
            (
                "get_mcp_prompt",
                "discovered_prompts",
                "取得 MCP 伺服器提供的 prompt 範本內容，作為完成任務的參考指引，只能使用下列 prompt：\n",
                lambda p: f"- {p['name']}{('：' + p['description']) if p.get('description') else ''}"
                + (f"（參數：{', '.join(a['name'] + ('*' if a.get('required') else '') for a in p.get('arguments') or [])}）" if p.get("arguments") else ""),
                {"name": {"type": "string", "description": "prompt 名稱"}, "arguments": {"type": "object", "description": "prompt 參數，值皆為字串"}},
            ),
        ):
            lines: List[str] = []
            servers_used: List[str] = []
            used = len(header)
            for server in servers:
                items = self._mcp_catalog(server, column)
                if not items:
                    continue
                section = [f"[{server.name}] {server.display_name}"] + [render(item) for item in items]
                text = "\n".join(section) + "\n"
                if used + len(text) > MAX_MCP_CATALOG_CHARS:
                    logger.warning(f"MCP {column} 目錄超過 {MAX_MCP_CATALOG_CHARS} 字，未列入伺服器：{server.name}")
                    continue
                used += len(text)
                lines.append(text)
                servers_used.append(server.name)
            if not servers_used:
                continue
            properties = {"server": {"type": "string", "enum": servers_used, "description": "MCP 伺服器名稱（方括號內）"}, **parameters}
            required = ["server", "uri"] if tool_name == "read_mcp_resource" else ["server", "name"]
            definitions.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": "[MCP 協定]" + header + "".join(lines),
                    "parameters": {"type": "object", "properties": properties, "required": required},
                },
            })
        return definitions
    @staticmethod
    def _find_mcp_catalog_server(db, name: str, arguments: Dict[str, Any]):
        from app.models import McpServer
        server = db.query(McpServer).filter(McpServer.name == str(arguments.get("server", "")), McpServer.is_enabled == True).first()
        if server is None:
            return None, None
        if name == "read_mcp_resource":
            uri = str(arguments.get("uri", ""))
            listed = any(r.get("uri") == uri for r in ResearchToolRegistry._mcp_catalog(server, "discovered_resources"))
            return (server, uri) if listed else (None, None)
        prompt_name = str(arguments.get("name", ""))
        listed = any(p.get("name") == prompt_name for p in ResearchToolRegistry._mcp_catalog(server, "discovered_prompts"))
        return (server, prompt_name) if listed else (None, None)
    @staticmethod
    def _mcp_target(server) -> str:
        if server.transport_type == "stdio":
            return f"本機指令 {os.path.basename(server.command or '')}"
        return f"{(server.transport_type or '').upper()} {_url_host(server.url or '')}"
    @staticmethod
    def _enabled_skills(user_id: Optional[int]) -> List[Any]:
        from app.models.database import SessionLocal
        from app.models import AgentSkill
        db = SessionLocal()
        try:
            skills = db.query(AgentSkill).filter(AgentSkill.is_enabled == True).order_by(AgentSkill.name).all()
            return [
                s for s in skills
                if agent_skills.skill_files_present(s.name) and agent_skills.skill_visible_to(s.allowed_user_ids, user_id)
            ]
        finally:
            db.close()
    def _skill_tool_definitions(self, user_id: Optional[int]) -> List[Dict[str, Any]]:
        header = (
            "載入管理員安裝的技能（Agent Skills）完整指示。當使用者的任務符合下列某個技能的描述時，"
            "先以技能名稱呼叫此工具取得指示，再依指示完成任務；不相關時不要呼叫。\n"
        )
        entries: List[str] = []
        names: List[str] = []
        script_names: List[str] = []
        used = len(header) + len("<available_skills>\n</available_skills>")
        for skill in self._enabled_skills(user_id):
            entry = f"  <skill>\n    <name>{skill.name}</name>\n    <description>{skill.description}</description>\n  </skill>\n"
            if used + len(entry) > MAX_SKILL_CATALOG_CHARS:
                logger.warning(f"技能目錄超過 {MAX_SKILL_CATALOG_CHARS} 字，未列入技能：{skill.name}")
                continue
            used += len(entry)
            entries.append(entry)
            names.append(skill.name)
            if skill.allow_scripts:
                script_names.append(skill.name)
        if not names:
            return []
        catalog = header + "<available_skills>\n" + "".join(entries) + "</available_skills>"
        return [
            {
                "type": "function",
                "function": {
                    "name": "activate_skill",
                    "description": catalog,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "enum": names, "description": "要載入的技能名稱"}
                        },
                        "required": ["name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_skill_resource",
                    "description": "讀取已載入技能目錄中的參考檔、範本或腳本內容（例如 references/REFERENCE.md）。只在技能指示提到該檔案時使用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill": {"type": "string", "enum": names, "description": "技能名稱"},
                            "path": {"type": "string", "description": "技能目錄內的相對路徑"}
                        },
                        "required": ["skill", "path"]
                    }
                }
            }
        ] + ([{
            "type": "function",
            "function": {
                "name": SKILL_SCRIPT_TOOL_NAME,
                "description": "在主機上執行已載入技能中的腳本（.py、.sh、.js），每次執行前需使用者核准；回傳結束碼、stdout 與 stderr。只在技能指示要求執行該腳本時使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill": {"type": "string", "enum": script_names, "description": "技能名稱"},
                        "path": {"type": "string", "description": "技能目錄內的腳本相對路徑，例如 scripts/extract.py"},
                        "args": {"type": "array", "items": {"type": "string"}, "description": "命令列參數"},
                        "stdin": {"type": "string", "description": "選填：傳給腳本的標準輸入"}
                    },
                    "required": ["skill", "path"]
                }
            }
        }] if script_names else [])
    def _visible_skill(self, name: str, user_id: Optional[int]):
        return next((skill for skill in self._enabled_skills(user_id) if skill.name == name), None)
    async def activate_skill(self, name: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        if await asyncio.to_thread(self._visible_skill, name, user_id) is None:
            return {"error": f"沒有啟用中的技能：{name}"}
        return await asyncio.to_thread(agent_skills.activate_skill, name)
    async def read_skill_resource(self, skill: str, path: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        if await asyncio.to_thread(self._visible_skill, skill, user_id) is None:
            return {"error": f"沒有啟用中的技能：{skill}"}
        return await asyncio.to_thread(agent_skills.read_skill_resource, skill, path)
    async def run_skill_script(self, arguments: Dict[str, Any], user_id: Optional[int] = None) -> Dict[str, Any]:
        name = str(arguments.get("skill", ""))
        skill = await asyncio.to_thread(self._visible_skill, name, user_id)
        if skill is None or not skill.allow_scripts:
            return {"error": f"技能「{name}」沒有啟用或不允許執行腳本"}
        try:
            return await agent_skills.run_skill_script(name, str(arguments.get("path", "")), arguments.get("args"), arguments.get("stdin"))
        except Exception as e:
            error_id = log_and_get_error_id(logger, f"執行技能 {name} 的腳本失敗", e)
            return {"error": f"執行技能腳本失敗（錯誤代碼：{error_id}）"}
    @staticmethod
    def _find_mcp_tool(db, name: str):
        """依 Agent 看到的函式名稱找出啟用中的 MCP 伺服器與其工具原名"""
        from app.models import McpServer
        for ms in db.query(McpServer).filter(McpServer.is_enabled == True).all():
            if not ms.discovered_tools:
                continue
            try:
                tools_list = json.loads(ms.discovered_tools)
            except Exception:
                continue
            clean_s = re.sub(r'[^a-zA-Z0-9_]', '_', ms.name).lower()
            for mt in tools_list:
                clean_t = re.sub(r'[^a-zA-Z0-9_]', '_', mt.get("name", "")).lower()
                if f"mcp_{clean_s}_{clean_t}" == name:
                    return ms, mt.get("name")
        return None, None
    def approval_requirement(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, str]]:
        """需要使用者核准的工具回傳顯示資訊，其餘（含內建工具與找不到的工具）回傳 None。
        target 說明實際送出的位置（HTTP 方法與主機、MCP 的傳輸方式與主機或指令），讓核准者知道資料會送到哪裡"""
        if name in BUILTIN_TOOL_NAMES:
            return None
        if name == SKILL_SCRIPT_TOOL_NAME:
            arguments = arguments or {}
            path = str(arguments.get("path", ""))
            interpreter = agent_skills.script_interpreter(PurePosixPath(path.replace("\\", "/")))
            program = os.path.basename(interpreter[0]) if interpreter else "?"
            return {"kind": "skill_script", "display_name": f"{arguments.get('skill', '')} → {path}", "target": f"本機指令 {program}"}
        from app.models.database import SessionLocal
        from app.models import CustomApiTool
        db = SessionLocal()
        try:
            if name in MCP_CATALOG_TOOL_NAMES:
                server, item = self._find_mcp_catalog_server(db, name, arguments or {})
                if server is not None and server.requires_approval:
                    return {"kind": "mcp", "display_name": f"{server.display_name} → {item}", "target": self._mcp_target(server)}
                return None
            if name.startswith("mcp_"):
                server, tool_name = self._find_mcp_tool(db, name)
                if server is not None and server.requires_approval:
                    return {"kind": "mcp", "display_name": f"{server.display_name} → {tool_name}", "target": self._mcp_target(server)}
                return None
            tool = db.query(CustomApiTool).filter(CustomApiTool.name == name, CustomApiTool.is_enabled == True).first()
            if tool is not None and tool.requires_approval:
                configured_url = tool.url or f"{(tool.base_url or '').rstrip('/')}/{(tool.path or '').lstrip('/')}"
                target = f"{(tool.method or 'GET').upper()} {_url_host(configured_url)}"
                return {"kind": "custom_api", "display_name": tool.display_name or tool.name, "target": target}
            return None
        finally:
            db.close()
    async def _execute_mcp_catalog_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        from app.models.database import SessionLocal
        from app.services.mcp_service import McpManager
        from app.api.mcp import _serialize_mcp_server
        try:
            db = SessionLocal()
            try:
                server, item = self._find_mcp_catalog_server(db, name, arguments)
                if server is None:
                    return {"error": "找不到啟用中的 MCP 伺服器，或 uri / prompt 不在該伺服器的清單中"}
                server_dict = _serialize_mcp_server(server)
            finally:
                db.close()
            if name == "read_mcp_resource":
                return await McpManager.read_mcp_resource(server_dict, item)
            prompt_arguments = arguments.get("arguments") or {}
            if not isinstance(prompt_arguments, dict):
                return {"error": "arguments 必須是物件"}
            return await McpManager.get_mcp_prompt(server_dict, item, {str(k): str(v) for k, v in prompt_arguments.items()})
        except Exception as e:
            error_id = log_and_get_error_id(logger, f"執行 {name} 時發生異常", e)
            return {"error": f"執行 MCP 請求失敗（錯誤代碼：{error_id}）"}
    async def execute_tool(self, name: str, arguments: Dict[str, Any], user_id: Optional[int] = None) -> Any:
        """執行指定名稱之工具並回傳結果"""
        if name in WEB_TOOL_NAMES and not settings.ENABLE_WEB_SEARCH:
            return {"error": f"聯網工具已停用（ENABLE_WEB_SEARCH=false）: {name}"}
        if name == "search_knowledge_base":
            query = arguments.get("query", "")
            top_k = int(arguments.get("top_k", 3))
            target_document = arguments.get("target_document")
            return await self.search_knowledge_base(query, top_k, target_document)
        elif name == "filter_and_count_records":
            date_range = arguments.get("date_range")
            author = arguments.get("author")
            keyword = arguments.get("keyword")
            target_document = arguments.get("target_document")
            limit = int(arguments.get("limit", 50))
            return await self.filter_and_count_records(date_range, author, keyword, target_document, limit)
        elif name == "web_search":
            query = arguments.get("query", "")
            max_results = int(arguments.get("max_results", 5))
            return await self.web_search(query, max_results)
        elif name == "web_fetch":
            url = arguments.get("url", "")
            return await self.web_fetch(url)
        elif name == "activate_skill":
            return await self.activate_skill(str(arguments.get("name", "")), user_id)
        elif name == "read_skill_resource":
            return await self.read_skill_resource(str(arguments.get("skill", "")), str(arguments.get("path", "")), user_id)
        elif name == SKILL_SCRIPT_TOOL_NAME:
            return await self.run_skill_script(arguments, user_id)
        elif name in MCP_CATALOG_TOOL_NAMES:
            return await self._execute_mcp_catalog_tool(name, arguments)
        elif name.startswith("mcp_"):

            try:
                from app.models.database import SessionLocal
                from app.models import McpServer
                from app.services.mcp_service import McpManager
                from app.api.mcp import _serialize_mcp_server
                db = SessionLocal()
                target_server, target_tool_name = self._find_mcp_tool(db, name)
                if target_server and target_tool_name:
                    s_dict = _serialize_mcp_server(target_server)
                    db.close()
                    res = await McpManager.execute_mcp_tool(s_dict, target_tool_name, arguments)
                    return res
                db.close()
                return {"error": f"找不到對應且啟用的 MCP 伺服器工具: {name}"}
            except Exception as e:
                error_id = log_and_get_error_id(logger, f"執行 MCP 工具 {name} 時發生異常", e)
                return {"error": f"執行 MCP 工具失敗（錯誤代碼：{error_id}）"}
        else:

            try:
                from app.models.database import SessionLocal
                from app.models import CustomApiTool
                from app.api.api_tools import execute_http_api_tool, _serialize_tool_model
                db = SessionLocal()
                custom_tool = db.query(CustomApiTool).filter(CustomApiTool.name == name).first()
                if custom_tool and custom_tool.is_enabled:
                    tool_dict = _serialize_tool_model(custom_tool)
                    db.close()
                    return await execute_http_api_tool(tool_dict, arguments, name)
                db.close()
            except Exception as e:
                error_id = log_and_get_error_id(logger, f"執行自訂 API 工具 {name} 時發生異常", e)
                return {"error": f"執行自訂 API 工具失敗（錯誤代碼：{error_id}）"}
            return {"error": f"未知的工具名稱: {name}"}
