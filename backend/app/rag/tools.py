import asyncio
import html
import json
import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urlparse
import httpx
from app import prompts
from app.core.config import settings
from app.core.domain_profile import domain_profile
from app.core.error_response import format_ssrf_rejection, log_and_get_error_id
from app.core.html_text import extract_readable_text, extract_text_and_title
from app.core.limits import MAX_KB_CATALOG_CHARS, MAX_MCP_CATALOG_CHARS, MAX_SKILL_CATALOG_CHARS, MAX_TEXT_CLEANUP_CHARS
from app.core.security_logging import log_fields
from app.rag.file_tools import FILE_TOOL_NAMES, execute_file_tool, file_tool_approval, file_tool_definitions
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
MCP_TOOL_PREFIX = "mcp_"
def _tool_kind(name: str) -> str:
    if name in BUILTIN_TOOL_NAMES:
        return "builtin"
    if name == SKILL_SCRIPT_TOOL_NAME:
        return "skill_script"
    if name in FILE_TOOL_NAMES:
        return "file"
    if name in MCP_CATALOG_TOOL_NAMES or name.startswith(MCP_TOOL_PREFIX):
        return "mcp"
    return "api"
def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
def is_web_fetch_domain_allowed(url: str) -> bool:
    allowed = settings.web_fetch_allowed_domains
    if allowed == ["*"]:
        return True
    host = (urlparse(url).hostname or "").rstrip(".")
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed)
KB_DESCRIPTION_CACHE_SECONDS = 60.0
_kb_description_lock = threading.Lock()
_kb_description_cache: Optional[Tuple[float, Tuple[str, List[str]]]] = None
def _url_host(url: str) -> str:
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
MAX_DATE_RANGE_CHARS = 200
MAX_TARGET_DATES = 93
MAX_FILTER_RECORDS = 50
def extract_html_text(html_content: str) -> Tuple[str, str]:
    title, text, _ = extract_text_and_title((html_content or "")[:MAX_TEXT_CLEANUP_CHARS])
    return title, text
def clean_html(html_content: str) -> str:
    return extract_html_text(html_content)[1][:4000]
def extract_page_text(html_content: str) -> Tuple[str, str]:
    return extract_readable_text((html_content or "")[:MAX_TEXT_CLEANUP_CHARS])
DUCKDUCKGO_LINK_CLASS = 'class="result__a"'
DUCKDUCKGO_SNIPPET_CLASS = 'class="result__snippet"'
HTML_HREF_PATTERN = re.compile(r'\bhref="([^"]*)"', re.IGNORECASE)
def _is_duckduckgo_host(host: Optional[str]) -> bool:
    host = (host or "").lower()
    return host == "duckduckgo.com" or host.endswith(".duckduckgo.com")
def _duckduckgo_target(href: str) -> Optional[str]:
    link = html.unescape(href)
    if link.startswith("//"):
        link = "https:" + link
    parsed = urlparse(link)
    if _is_duckduckgo_host(parsed.hostname):
        link = (parse_qs(parsed.query).get("uddg") or [""])[0]
        parsed = urlparse(link)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or _is_duckduckgo_host(parsed.hostname):
        return None
    return link
def _duckduckgo_snippet(page: str, position: int, block_end: int) -> str:
    snippet_class = page.find(DUCKDUCKGO_SNIPPET_CLASS, position, block_end)
    if snippet_class < 0:
        return ""
    tag_start = page.rfind("<", position, snippet_class)
    tag_end = page.find(">", snippet_class, block_end)
    if tag_start < 0 or tag_end < 0:
        return ""
    name = page[tag_start + 1:snippet_class].split()[0].lower()
    close = page.find(f"</{name}>", tag_end, block_end)
    return clean_html(page[tag_end + 1:close]) if close >= 0 else ""
def parse_duckduckgo_results(page: str, max_results: int) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    block_start = 0
    link_class = page.find(DUCKDUCKGO_LINK_CLASS)
    while link_class >= 0 and len(results) < max_results:
        next_link_class = page.find(DUCKDUCKGO_LINK_CLASS, link_class + len(DUCKDUCKGO_LINK_CLASS))
        block_end = next_link_class if next_link_class >= 0 else len(page)
        tag_start = page.rfind("<", block_start, link_class)
        tag_end = page.find(">", link_class, block_end)
        title_end = page.find("</a>", tag_end, block_end) if tag_end >= 0 else -1
        if tag_start >= 0 and title_end >= 0:
            href = HTML_HREF_PATTERN.search(page, tag_start, tag_end)
            url = _duckduckgo_target(href.group(1)) if href else None
            title = clean_html(page[tag_end + 1:title_end])
            if url and title:
                results.append({"title": title, "url": url, "snippet": _duckduckgo_snippet(page, title_end, block_end)})
        block_start = link_class + len(DUCKDUCKGO_LINK_CLASS)
        link_class = next_link_class
    return results
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
    def __init__(self, retriever=None):
        self.retriever = retriever
    def set_retriever(self, retriever):
        self.retriever = retriever
    async def search_knowledge_base(self, query: str, top_k: int = 3, target_document: Optional[str] = None) -> Dict[str, Any]:
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
        if not self.retriever or not hasattr(self.retriever, "vector_store") or not self.retriever.vector_store.documents:
            return {"error": "知識庫尚未載入", "total_count": 0, "records": []}
        if date_range and len(date_range) > MAX_DATE_RANGE_CHARS:
            return {"error": f"date_range 不可超過 {MAX_DATE_RANGE_CHARS} 個字元", "total_count": 0, "records": []}
        try:
            limit = max(1, min(int(limit), MAX_FILTER_RECORDS))
        except (TypeError, ValueError):
            limit = MAX_FILTER_RECORDS
        try:
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
                        logger.warning(f"Ollama Web Search API 回傳狀態碼 {resp.status_code}，切換至備援引擎")
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
                    results = parse_duckduckgo_results(resp.text[:MAX_TEXT_CLEANUP_CHARS], max_results)
                    if not results:
                        logger.warning(f"DuckDuckGo 回應中解析不到搜尋結果（{len(resp.text)} 字元）")
                        return {
                            "query": query,
                            "engine": "duckduckgo_fallback",
                            "error": "搜尋引擎沒有回傳可解析的結果（可能查無資料、暫時被阻擋，或結果頁格式已變更），請換關鍵字或改用其他資料回答",
                            "results": []
                        }
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
        from app.core.ssrf_protection import DnsPool, safe_fetch_text, validate_url_ssrf, SSRFProtectionError
        if not is_web_fetch_domain_allowed(url):
            return {"url": url, "error": "該網址的網域不在 WEB_FETCH_ALLOWED_DOMAINS 允許清單內", "content": ""}
        is_safe, error_msg, _ = await validate_url_ssrf(url, DnsPool.USER_URL)
        if not is_safe:
            error_id = log_and_get_error_id(
                logger, f"web_fetch 網址被 SSRF 防護拒絕: {error_msg}", SSRFProtectionError(error_msg), logging.WARNING
            )
            return {"url": url, "error": format_ssrf_rejection(error_id), "content": ""}
        ollama_key = settings.OLLAMA_API_KEY or ''
        if ollama_key and settings.web_fetch_allowed_domains == ["*"]:
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
                max_size_bytes=5 * 1024 * 1024,
                is_url_allowed=is_web_fetch_domain_allowed
            )
            title, clean_text = await asyncio.to_thread(extract_page_text, raw_html)
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
                rows = db.query(Document.id, Document.filename, Document.description, Document.file_type).order_by(Document.id).all()
                for row in rows:
                    desc = row.description
                    if not desc:
                        content = db.query(Document.content).filter(Document.id == row.id).scalar()
                        if content:
                            desc = DocumentProcessor.generate_document_summary(row.filename, content, row.file_type or "")
                    doc_items.append((row.filename, desc or prompts.DOCUMENT_PLACEHOLDER_SUMMARY.format(filename=row.filename)))
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
            return prompts.KNOWLEDGE_BASE_SEARCH, []
        doc_descriptions = []
        filenames: List[str] = []
        catalog_chars = 0
        for idx, (filename, desc) in enumerate(doc_items, start=1):
            line = prompts.KNOWLEDGE_BASE_ENTRY.format(index=idx, filename=filename, description=desc)
            catalog_chars += len(line)
            if catalog_chars > MAX_KB_CATALOG_CHARS:
                doc_descriptions.append(prompts.KNOWLEDGE_BASE_UNLISTED.format(count=len(doc_items) - idx + 1))
                filenames = []
                break
            doc_descriptions.append(line)
            filenames.append(filename)
        return prompts.KNOWLEDGE_BASE_SEARCH + prompts.KNOWLEDGE_BASE_CATALOG.format(catalog="\n".join(doc_descriptions)), filenames
    def get_tool_definitions(
        self, user_id: Optional[int] = None, conversation_id: Optional[int] = None, requested_skill: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        kb_desc, doc_names = self._generate_knowledge_base_description()
        target_document_schema: Dict[str, Any] = {
            "type": "string",
            "description": prompts.TARGET_DOCUMENT
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
                                "description": prompts.SEARCH_QUERY
                            },
                            "target_document": target_document_schema,
                            "top_k": {
                                "type": "integer",
                                "description": prompts.SEARCH_TOP_K.format(max_k=settings.FINAL_K),
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
                    "description": prompts.FILTER_RECORDS,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date_range": {
                                "type": "string",
                                "description": prompts.FILTER_DATE_RANGE
                            },
                            "author": {
                                "type": "string",
                                "description": prompts.FILTER_AUTHOR
                            },
                            "keyword": {
                                "type": "string",
                                "description": prompts.FILTER_KEYWORD
                            },
                            "target_document": target_document_schema,
                            "limit": {
                                "type": "integer",
                                "description": prompts.FILTER_LIMIT.format(max_records=MAX_FILTER_RECORDS),
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
                    "description": prompts.WEB_SEARCH,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": prompts.WEB_SEARCH_QUERY
                            },
                            "max_results": {
                                "type": "integer",
                                "description": prompts.WEB_SEARCH_MAX_RESULTS,
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
                    "description": prompts.WEB_FETCH,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": prompts.WEB_FETCH_URL
                            }
                        },
                        "required": ["url"]
                    }
                }
            }
        ]
        if not settings.ENABLE_WEB_SEARCH:
            base_tools = [t for t in base_tools if t["function"]["name"] not in WEB_TOOL_NAMES]
        if conversation_id is not None:
            base_tools.extend(file_tool_definitions())
        try:
            base_tools.extend(self._skill_tool_definitions(user_id, requested_skill))
        except Exception as e:
            logger.warning(f"載入 Agent Skills 失敗: {e}")
        try:
            from app.models.database import SessionLocal
            from app.models import CustomApiTool, McpServer
            from app.services.mcp_service import McpManager
            from app.services.openapi_parser import fit_tool_name
            db = SessionLocal()
            custom_tools = db.query(CustomApiTool).filter(CustomApiTool.is_enabled == True).order_by(CustomApiTool.id).all()
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
                        "name": fit_tool_name(ct.name),
                        "description": prompts.CUSTOM_API_TOOL.format(display_name=ct.display_name, description=desc),
                        "parameters": p_schema
                    }
                })
            mcp_servers = db.query(McpServer).filter(McpServer.is_enabled == True).order_by(McpServer.id).all()
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
                            if fdef is not None:
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
                prompts.MCP_RESOURCE_CATALOG,
                lambda r: f"- {r['uri']}｜{r.get('name') or ''}{('：' + r['description']) if r.get('description') else ''}",
                {"uri": {"type": "string", "description": prompts.MCP_RESOURCE_URI}},
            ),
            (
                "get_mcp_prompt",
                "discovered_prompts",
                prompts.MCP_PROMPT_CATALOG,
                lambda p: f"- {p['name']}{('：' + p['description']) if p.get('description') else ''}"
                + (f"（參數：{', '.join(a['name'] + ('*' if a.get('required') else '') for a in p.get('arguments') or [])}）" if p.get("arguments") else ""),
                {"name": {"type": "string", "description": prompts.MCP_PROMPT_NAME}, "arguments": {"type": "object", "description": prompts.MCP_PROMPT_ARGUMENTS}},
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
            properties = {"server": {"type": "string", "enum": servers_used, "description": prompts.MCP_SERVER}, **parameters}
            required = ["server", "uri"] if tool_name == "read_mcp_resource" else ["server", "name"]
            definitions.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": header + "".join(lines),
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
    def _skill_tool_definitions(self, user_id: Optional[int], requested_skill: Optional[str]) -> List[Dict[str, Any]]:
        header = prompts.SKILL_CATALOG
        entries: List[str] = []
        names: List[str] = []
        script_names: List[str] = []
        used = len(header) + len("<available_skills>\n</available_skills>")
        for skill in sorted(self._enabled_skills(user_id), key=lambda skill: skill.name != requested_skill):
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
                            "name": {"type": "string", "enum": names, "description": prompts.ACTIVATE_SKILL_NAME}
                        },
                        "required": ["name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_skill_resource",
                    "description": prompts.READ_SKILL_RESOURCE,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill": {"type": "string", "enum": names, "description": prompts.SKILL_NAME},
                            "path": {"type": "string", "description": prompts.SKILL_RESOURCE_PATH}
                        },
                        "required": ["skill", "path"]
                    }
                }
            }
        ] + ([{
            "type": "function",
            "function": {
                "name": SKILL_SCRIPT_TOOL_NAME,
                "description": prompts.RUN_SKILL_SCRIPT,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill": {"type": "string", "enum": script_names, "description": prompts.SKILL_NAME},
                        "path": {"type": "string", "description": prompts.SKILL_SCRIPT_PATH},
                        "args": {"type": "array", "items": {"type": "string"}, "description": prompts.SKILL_SCRIPT_ARGS},
                        "stdin": {"type": "string", "description": prompts.SKILL_SCRIPT_STDIN}
                    },
                    "required": ["skill", "path"]
                }
            }
        }] if script_names else [])
    def _visible_skill(self, name: str, user_id: Optional[int]):
        return next((skill for skill in self._enabled_skills(user_id) if skill.name == name), None)
    async def activate_skill(self, name: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        skill = await asyncio.to_thread(self._visible_skill, name, user_id)
        if skill is None:
            return {"error": f"沒有啟用中的技能：{name}"}
        return await asyncio.to_thread(agent_skills.activate_skill, name, bool(skill.allow_scripts))
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
        from app.models import McpServer
        from app.services.mcp_service import mcp_function_name
        for ms in db.query(McpServer).filter(McpServer.is_enabled == True).all():
            if not ms.discovered_tools:
                continue
            try:
                tools_list = json.loads(ms.discovered_tools)
            except Exception:
                continue
            for mt in tools_list:
                if mcp_function_name(ms.name, mt.get("name", "")) == name:
                    return ms, mt.get("name")
        return None, None
    @staticmethod
    def _find_custom_api_tool(db, name: str):
        from app.models import CustomApiTool
        from app.services.openapi_parser import fit_tool_name
        for tool in db.query(CustomApiTool).filter(CustomApiTool.is_enabled == True).all():
            if fit_tool_name(tool.name) == name:
                return tool
        return None
    def approval_requirement(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
    ) -> Optional[Dict[str, str]]:
        if name in BUILTIN_TOOL_NAMES:
            return None
        if name in FILE_TOOL_NAMES:
            return file_tool_approval(name, arguments or {}, user_id, conversation_id)
        if name == SKILL_SCRIPT_TOOL_NAME:
            arguments = arguments or {}
            path = str(arguments.get("path", ""))
            interpreter = agent_skills.script_interpreter(PurePosixPath(path.replace("\\", "/")))
            program = os.path.basename(interpreter[0]) if interpreter else "?"
            return {"kind": "skill_script", "display_name": f"{arguments.get('skill', '')} → {path}", "target": f"本機指令 {program}"}
        from app.models.database import SessionLocal
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
            tool = self._find_custom_api_tool(db, name)
            if tool is not None and tool.requires_approval:
                configured_url = tool.url or f"{(tool.base_url or '').rstrip('/')}/{(tool.path or '').lstrip('/')}"
                target = f"{(tool.method or 'GET').upper()} {_url_host(configured_url)}"
                if tool.workflow_definition:
                    try:
                        steps = json.loads(tool.workflow_definition).get("step_targets") or []
                    except (ValueError, AttributeError):
                        steps = []
                    target = f"Arazzo 工作流程：{'、'.join(steps) or '（沒有可執行的步驟）'}"
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
    async def execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        user_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
    ) -> Any:
        fields = {"tool": name, "kind": _tool_kind(name), "arg_keys": ",".join(map(str, arguments)) or None}
        started = time.perf_counter()
        try:
            result = await self._dispatch_tool(name, arguments, user_id, conversation_id)
        except asyncio.CancelledError:
            logger.info("工具呼叫中止 %s", log_fields(**fields, status="cancelled", duration_ms=_elapsed_ms(started)))
            raise
        except Exception as e:
            logger.warning("工具呼叫失敗 %s", log_fields(**fields, status="exception", duration_ms=_elapsed_ms(started), error=type(e).__name__))
            raise
        is_error = isinstance(result, dict) and "error" in result
        logger.log(
            logging.WARNING if is_error else logging.INFO,
            "工具呼叫完成 %s",
            log_fields(
                **fields,
                status="error" if is_error else "ok",
                duration_ms=_elapsed_ms(started),
                result_chars=len(json.dumps(result, ensure_ascii=False, default=str)),
                error=result["error"] if is_error else None,
            ),
        )
        return result
    async def _dispatch_tool(self, name: str, arguments: Dict[str, Any], user_id: Optional[int], conversation_id: Optional[int]) -> Any:
        if name in FILE_TOOL_NAMES:
            return await execute_file_tool(name, arguments, user_id, conversation_id)
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
        elif name.startswith(MCP_TOOL_PREFIX):
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
                from app.api.api_tools import execute_api_tool, _serialize_tool_model
                db = SessionLocal()
                custom_tool = self._find_custom_api_tool(db, name)
                if custom_tool:
                    tool_dict = _serialize_tool_model(custom_tool)
                    db.close()
                    return await execute_api_tool(tool_dict, arguments, name)
                db.close()
            except Exception as e:
                error_id = log_and_get_error_id(logger, f"執行自訂 API 工具 {name} 時發生異常", e)
                return {"error": f"執行自訂 API 工具失敗（錯誤代碼：{error_id}）"}
            return {"error": f"未知的工具名稱: {name}"}