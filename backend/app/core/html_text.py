"""以單次線性掃描從 HTML 取出文字。

回溯型正規式（例如 `<[^>]+>`、`<script[\\s\\S]*?</script>`）與標準函式庫的 html.parser
遇到大量未閉合的 `<` 或 `<script` 時都會呈二次時間；這裡只用 str.find 前進，
每個位置最多被掃描常數次。輸出只供檢索與模型閱讀，不追求完整的 HTML 語意。
"""
import html
import string
from typing import List, Optional, Set, Tuple

SKIPPED_TAGS = ("script", "style", "noscript")
BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "br", "section", "article"}
PAGE_CHROME_TAGS = ("nav", "aside", "header", "footer")
PAGE_CHROME_ROLES = ("navigation", "complementary", "banner", "contentinfo")
MAIN_CONTENT_CHROME_TAGS = ("nav", "aside")
MAIN_CONTENT_CHROME_ROLES = ("navigation", "complementary")
ASCII_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


def _tag_name(tag_body: str) -> Tuple[str, bool]:
    """回傳 (小寫標籤名稱, 是否為結尾標籤)"""
    closing = tag_body.startswith("/")
    body = tag_body[1:] if closing else tag_body
    end = 0
    while end < len(body) and (body[end].isalnum() or body[end] in "-:"):
        end += 1
    return body[:end].lower(), closing


def _find_tag(lowered: str, prefix: str, position: int) -> int:
    while True:
        index = lowered.find(prefix, position)
        if index < 0:
            return -1
        after = index + len(prefix)
        if after >= len(lowered) or not (lowered[after].isalnum() or lowered[after] in "-:"):
            return index
        position = after


def _element_end(lowered: str, name: str, position: int) -> int:
    depth = 1
    next_open = _find_tag(lowered, f"<{name}", position)
    while True:
        close = _find_tag(lowered, f"</{name}", position)
        if close < 0:
            return -1
        while 0 <= next_open < close:
            depth += 1
            next_open = _find_tag(lowered, f"<{name}", next_open + len(name) + 1)
        depth -= 1
        position = close + len(name) + 2
        if depth == 0:
            end = lowered.find(">", position)
            return -1 if end < 0 else end + 1


def _has_role(tag_body: str, roles: Tuple[str, ...]) -> bool:
    return any(f'role="{role}"' in tag_body or f"role='{role}'" in tag_body for role in roles)


def _element_range(lowered: str, start: int) -> Optional[Tuple[int, int]]:
    open_end = lowered.find(">", start)
    if open_end < 0:
        return None
    name, _ = _tag_name(lowered[start + 1:open_end])
    end = _element_end(lowered, name, open_end + 1) if name else -1
    return (start, end) if end >= 0 else None


def _main_content_range(lowered: str) -> Optional[Tuple[int, int]]:
    main_start = _find_tag(lowered, "<main", 0)
    main_range = _element_range(lowered, main_start) if main_start >= 0 else None
    if main_range:
        return main_range
    role_indexes = [index for index in (lowered.find('role="main"'), lowered.find("role='main'")) if index >= 0]
    role_start = lowered.rfind("<", 0, min(role_indexes)) if role_indexes else -1
    role_range = _element_range(lowered, role_start) if role_start >= 0 else None
    if role_range:
        return role_range
    article_start = _find_tag(lowered, "<article", 0)
    article_close = lowered.rfind("</article")
    article_end = lowered.find(">", article_close) if 0 <= article_start < article_close else -1
    if article_end >= 0:
        return article_start, article_end + 1
    return None


def _first_title(document: str, lowered: str) -> str:
    start = _find_tag(lowered, "<title", 0)
    open_end = lowered.find(">", start) if start >= 0 else -1
    close = lowered.find("</title", open_end) if open_end >= 0 else -1
    if close < 0:
        return ""
    return " ".join(html.unescape(document[open_end + 1:close]).split())


def extract_text_and_title(document: str) -> Tuple[str, str, List[str]]:
    """回傳 (title, 以空白串接的文字, 以區塊標籤分段的文字片段)"""
    return _extract(document, (), ())


def extract_readable_text(document: str) -> Tuple[str, str]:
    if not document:
        return "", ""
    lowered = document.translate(ASCII_LOWER)
    content_range = _main_content_range(lowered)
    if content_range:
        content = document[content_range[0]:content_range[1]]
        _, text, _ = _extract(content, MAIN_CONTENT_CHROME_TAGS, MAIN_CONTENT_CHROME_ROLES)
        if text:
            return _first_title(document, lowered), text
    title, text, _ = _extract(document, PAGE_CHROME_TAGS, PAGE_CHROME_ROLES)
    return title, text


def _extract(document: str, chrome_tags: Tuple[str, ...], chrome_roles: Tuple[str, ...]) -> Tuple[str, str, List[str]]:
    if not document:
        return "", "", []
    lowered = document.translate(ASCII_LOWER)
    unbalanced: Set[str] = set()
    parts: List[str] = []
    title = ""
    position = 0
    length = len(document)
    while position < length:
        start = document.find("<", position)
        if start < 0:
            parts.append(document[position:])
            break
        parts.append(document[position:start])
        end = document.find(">", start + 1)
        if end < 0:
            parts.append(document[start:])
            break
        name, closing = _tag_name(document[start + 1:end])
        position = end + 1
        if not closing and name in SKIPPED_TAGS + ("title",):
            close_start = lowered.find(f"</{name}", position)
            if close_start < 0:
                if name == "title":
                    title = title or document[position:]
                break
            if name == "title":
                title = title or document[position:close_start]
                parts.append(" " + document[position:close_start] + " ")
            close_end = document.find(">", close_start)
            if close_end < 0:
                break
            position = close_end + 1
            continue
        is_chrome = name in chrome_tags or (chrome_roles and "role=" in lowered[start:end] and _has_role(lowered[start:end], chrome_roles))
        if not closing and name and is_chrome and name not in unbalanced:
            element_end = _element_end(lowered, name, position)
            if element_end >= 0:
                parts.append("\n")
                position = element_end
                continue
            unbalanced.add(name)
        parts.append("\n" if name in BLOCK_TAGS else " ")
    raw = html.unescape("".join(parts))
    blocks = [" ".join(block.split()) for block in raw.split("\n")]
    blocks = [block for block in blocks if block]
    return " ".join(html.unescape(title).split()), " ".join(blocks), blocks
