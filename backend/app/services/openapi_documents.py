import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urldefrag, urljoin, urlparse
import yaml
from app.core.error_response import SafeClientError, format_ssrf_rejection, log_and_get_error_id
from app.core.limits import (
    MAX_OPENAPI_DOCUMENT_BYTES,
    MAX_OPENAPI_EXTERNAL_DOCUMENTS,
    MAX_OPENAPI_TOTAL_BYTES,
    OPENAPI_FETCH_MAX_REDIRECTS,
    OPENAPI_FETCH_TIMEOUT_SECONDS,
)
from app.core.ssrf_protection import DnsPool, SSRFProtectionError, safe_fetch_text
logger = logging.getLogger(__name__)
INLINE_DOCUMENT_URI = "urn:askmiao:inline-document"
SCHEMA_ID_KEYS = ("$id",)
ANCHOR_KEYS = ("$anchor", "$dynamicAnchor")
def load_yaml_without_aliases(text: str) -> Any:
    for event in yaml.parse(text, Loader=yaml.SafeLoader):
        if isinstance(event, yaml.AliasEvent):
            raise SafeClientError("規格不可使用 YAML 別名（*alias）")
    return yaml.safe_load(text)
def parse_document_text(text: str) -> Any:
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        try:
            return json.loads(text)
        except ValueError:
            pass
    try:
        return load_yaml_without_aliases(text)
    except SafeClientError:
        raise
    except Exception as e:
        raise SafeClientError(f"無法將內容解析為 JSON 或 YAML: {e}")
def is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")
def is_remote_uri(uri: str) -> bool:
    return urlparse(uri).scheme in ("http", "https")
def join_uri(base: str, ref: str) -> str:
    if ref.startswith("#"):
        return urldefrag(base)[0] + ref
    if is_remote_uri(ref) or not is_remote_uri(base):
        return ref if is_remote_uri(ref) else f"{urldefrag(base)[0]}|{ref}"
    return urljoin(base, ref)
def decode_pointer(fragment: str) -> List[str]:
    if not fragment or fragment == "/":
        return [] if not fragment else [""]
    return [unquote(part).replace("~1", "/").replace("~0", "~") for part in fragment.lstrip("/").split("/")]
def walk_pointer(node: Any, fragment: str) -> Any:
    for part in decode_pointer(fragment):
        if isinstance(node, dict):
            node = node[part]
        elif isinstance(node, list):
            node = node[int(part)]
        else:
            raise KeyError(part)
    return node
@dataclass
class SpecDocuments:
    root: Any
    root_uri: str
    retrieval_url: Optional[str]
    documents: Dict[str, Any] = field(default_factory=dict)
    resources: Dict[str, Any] = field(default_factory=dict)
    anchors: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    def register(self, uri: str, document: Any) -> None:
        self.documents[uri] = document
        self._index(document, uri)
    def _index(self, node: Any, base: str) -> None:
        stack: List[Tuple[Any, str]] = [(node, base)]
        while stack:
            current, current_base = stack.pop()
            if isinstance(current, dict):
                schema_id = current.get("$id")
                if isinstance(schema_id, str) and schema_id:
                    current_base = urldefrag(join_uri(current_base, schema_id))[0]
                    self.resources.setdefault(current_base, current)
                for key in ANCHOR_KEYS:
                    anchor = current.get(key)
                    if isinstance(anchor, str) and anchor:
                        self.anchors.setdefault(f"{urldefrag(current_base)[0]}#{anchor}", current)
                for value in current.values():
                    if isinstance(value, (dict, list)):
                        stack.append((value, current_base))
            elif isinstance(current, list):
                stack.extend((item, current_base) for item in current if isinstance(item, (dict, list)))
    def resolve(self, ref: str, base: str) -> Tuple[Any, str]:
        if not isinstance(ref, str):
            raise KeyError(ref)
        target = join_uri(base, ref)
        doc_uri, fragment = urldefrag(target)
        if doc_uri in self.resources:
            resource = self.resources[doc_uri]
        elif doc_uri in self.documents:
            resource = self.documents[doc_uri]
        else:
            raise KeyError(target)
        if fragment and not fragment.startswith("/"):
            anchored = self.anchors.get(f"{doc_uri}#{fragment}")
            if anchored is None:
                raise KeyError(target)
            return anchored, doc_uri
        return walk_pointer(resource, fragment), doc_uri
def _external_refs(node: Any, base: str) -> List[str]:
    found: List[str] = []
    stack: List[Tuple[Any, str]] = [(node, base)]
    while stack:
        current, current_base = stack.pop()
        if isinstance(current, dict):
            schema_id = current.get("$id")
            if isinstance(schema_id, str) and schema_id:
                current_base = urldefrag(join_uri(current_base, schema_id))[0]
            ref = current.get("$ref")
            if isinstance(ref, str) and not ref.startswith("#"):
                found.append(urldefrag(join_uri(current_base, ref))[0])
            stack.extend((value, current_base) for value in current.values() if isinstance(value, (dict, list)))
        elif isinstance(current, list):
            stack.extend((item, current_base) for item in current if isinstance(item, (dict, list)))
    return found
async def fetch_document_text(url: str, purpose: str) -> str:
    try:
        return await safe_fetch_text(
            url=url,
            dns_pool=DnsPool.CONFIGURED_ENDPOINT,
            timeout=OPENAPI_FETCH_TIMEOUT_SECONDS,
            max_redirects=OPENAPI_FETCH_MAX_REDIRECTS,
            max_size_bytes=MAX_OPENAPI_DOCUMENT_BYTES,
        )
    except SSRFProtectionError as e:
        error_id = log_and_get_error_id(logger, f"{purpose}網址被 SSRF 防護拒絕", e, logging.WARNING)
        raise SafeClientError(format_ssrf_rejection(error_id))
    except Exception as e:
        error_id = log_and_get_error_id(logger, f"取得{purpose}失敗", e)
        raise SafeClientError(f"取得{purpose}失敗，請確認網址可公開存取且能正常回應（錯誤代碼：{error_id}）")
async def load_source(text_or_url: str, purpose: str) -> Tuple[Any, Optional[str], int]:
    raw = text_or_url.strip()
    url = None
    if is_url(raw):
        url = raw
        raw = await fetch_document_text(url, purpose)
    if len(raw.encode("utf-8")) > MAX_OPENAPI_DOCUMENT_BYTES:
        raise SafeClientError(f"{purpose}超過 {MAX_OPENAPI_DOCUMENT_BYTES // (1024 * 1024)} MB 上限")
    document = parse_document_text(raw)
    if not isinstance(document, dict):
        raise SafeClientError(f"{purpose}格式無效，必須是 JSON 或 YAML 物件")
    return document, url, len(raw.encode("utf-8"))
def document_base(document: Dict[str, Any], retrieval_url: Optional[str]) -> str:
    base = retrieval_url or INLINE_DOCUMENT_URI
    self_uri = document.get("$self")
    if isinstance(self_uri, str) and self_uri and "#" not in self_uri:
        base = join_uri(base, self_uri) if (is_remote_uri(base) or is_remote_uri(self_uri)) else self_uri
    return urldefrag(base)[0]
async def build_documents(root: Dict[str, Any], retrieval_url: Optional[str], root_bytes: int) -> SpecDocuments:
    root_uri = document_base(root, retrieval_url)
    docs = SpecDocuments(root=root, root_uri=root_uri, retrieval_url=retrieval_url)
    docs.register(root_uri, root)
    if retrieval_url and urldefrag(retrieval_url)[0] != root_uri:
        docs.documents[urldefrag(retrieval_url)[0]] = root
    total = root_bytes
    queue = list(dict.fromkeys(_external_refs(root, root_uri)))
    fetched = 0
    while queue:
        uri = queue.pop(0)
        if uri in docs.documents or uri in docs.resources:
            continue
        if not is_remote_uri(uri):
            docs.warnings.append(f"無法解析相對參照 {uri.split('|', 1)[-1]}：貼上規格內容時沒有可依據的網址，請改用規格網址匯入")
            docs.documents[uri] = None
            continue
        if fetched >= MAX_OPENAPI_EXTERNAL_DOCUMENTS:
            docs.warnings.append(f"外部參照文件超過 {MAX_OPENAPI_EXTERNAL_DOCUMENTS} 份，其餘未載入")
            break
        fetched += 1
        try:
            text = await fetch_document_text(uri, "外部參照文件")
            total += len(text.encode("utf-8"))
            if total > MAX_OPENAPI_TOTAL_BYTES:
                raise SafeClientError(f"規格與外部參照文件合計超過 {MAX_OPENAPI_TOTAL_BYTES // (1024 * 1024)} MB 上限")
            document = parse_document_text(text)
        except SafeClientError as e:
            docs.warnings.append(f"外部參照文件 {uri} 無法載入：{e}")
            docs.documents[uri] = None
            continue
        docs.register(uri, document)
        queue.extend(ref for ref in _external_refs(document, uri) if ref not in docs.documents)
    return docs