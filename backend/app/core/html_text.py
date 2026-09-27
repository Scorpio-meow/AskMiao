"""以單次線性掃描從 HTML 取出文字。

回溯型正規式（例如 `<[^>]+>`、`<script[\\s\\S]*?</script>`）與標準函式庫的 html.parser
遇到大量未閉合的 `<` 或 `<script` 時都會呈二次時間；這裡只用 str.find 前進，
每個位置最多被掃描常數次。輸出只供檢索與模型閱讀，不追求完整的 HTML 語意。
"""
import html
from typing import List, Tuple

SKIPPED_TAGS = ("script", "style", "noscript")
BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "br", "section", "article"}


def _tag_name(tag_body: str) -> Tuple[str, bool]:
    """回傳 (小寫標籤名稱, 是否為結尾標籤)"""
    closing = tag_body.startswith("/")
    body = tag_body[1:] if closing else tag_body
    end = 0
    while end < len(body) and (body[end].isalnum() or body[end] in "-:"):
        end += 1
    return body[:end].lower(), closing


def extract_text_and_title(document: str) -> Tuple[str, str, List[str]]:
    """回傳 (title, 以空白串接的文字, 以區塊標籤分段的文字片段)"""
    if not document:
        return "", "", []
    lowered = document.lower()
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
                    title = document[position:]
                break
            if name == "title":
                title = document[position:close_start]
                parts.append(" " + title + " ")
            close_end = document.find(">", close_start)
            if close_end < 0:
                break
            position = close_end + 1
            continue
        parts.append("\n" if name in BLOCK_TAGS else " ")
    raw = html.unescape("".join(parts))
    blocks = [" ".join(block.split()) for block in raw.split("\n")]
    blocks = [block for block in blocks if block]
    return " ".join(html.unescape(title).split()), " ".join(blocks), blocks
