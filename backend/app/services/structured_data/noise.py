import re
from typing import Optional

JSON_DECLARATION_PATTERN = re.compile(r'(?:\b(?:const|let|var)\s+\w+\s*=|module\.exports\s*=)\s*')
BASE64_IMAGE_PATTERN = re.compile(r'data:image\/[a-zA-Z]+;base64,[a-zA-Z0-9+/=]{100,}')
BASE64_IMAGE_PLACEHOLDER = "[BASE64_IMAGE_OMITTED]"
SVG_PLACEHOLDER = "[SVG_ICON_OMITTED]"
SVG_OPEN = "<svg"
SVG_CLOSE = "</svg>"


def find_declared_json(text: str) -> Optional[str]:
    match = JSON_DECLARATION_PATTERN.search(text)
    if not match:
        return None
    rest = text[match.end():]
    closing = {"[": "]", "{": "}"}.get(rest[:1])
    if closing is None:
        return None
    end = rest.rfind(closing)
    return rest[:end + 1] if end >= 0 else None


def _extract_declared_json(text: str) -> str:
    body = find_declared_json(text)
    return body if body is not None else text.strip()


def _replace_svg_blocks(text: str) -> str:
    parts = []
    position = 0
    while True:
        start = text.find(SVG_OPEN, position)
        if start < 0:
            break
        end = text.find(SVG_CLOSE, start)
        if end < 0:
            break
        parts.append(text[position:start])
        parts.append(SVG_PLACEHOLDER)
        position = end + len(SVG_CLOSE)
    parts.append(text[position:])
    return "".join(parts)


def clean_noise(text: str) -> str:
    return _replace_svg_blocks(BASE64_IMAGE_PATTERN.sub(BASE64_IMAGE_PLACEHOLDER, text))
