import csv
import io
import threading
from collections import OrderedDict
from datetime import date, datetime, time
from typing import Any, Callable, Dict, Hashable, Iterator, List, Optional
import pymupdf
from docx import Document as WordDocument
from docx.table import Table
from docx.text.hyperlink import Hyperlink
from openpyxl import load_workbook
from pptx import Presentation
from pptx.shapes.picture import Picture
from app.core.limits import (
    FILE_PREVIEW_ITEMS,
    FILE_PREVIEW_PAGE_DPI,
    FILE_PREVIEW_PAGE_MAX_PIXELS,
    FILE_PREVIEW_PDF_CACHE_ENTRIES,
    FILE_PREVIEW_SHEET_COLUMNS,
    FILE_PREVIEW_SHEET_ROWS,
    FILE_PREVIEW_TEXT_CHARS,
    ExtractionLimits,
)
from app.services.conversation_files import ConversationFileError, extension_of
from app.services.file_builders import decode_text, with_checked_file
HTML_EXTENSIONS = (".html", ".htm")
MARKDOWN_EXTENSIONS = (".md", ".markdown")
UNSUPPORTED = "這種檔案無法預覽，請下載後開啟"
class RecentFiles:
    def __init__(self, size: int):
        self._size = size
        self._items: "OrderedDict[Hashable, bytes]" = OrderedDict()
        self._lock = threading.Lock()
    def get(self, key: Hashable, load: Callable[[], bytes]) -> bytes:
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]
        data = load()
        with self._lock:
            self._items[key] = data
            self._items.move_to_end(key)
            while len(self._items) > self._size:
                self._items.popitem(last=False)
        return data
recent_pdfs = RecentFiles(FILE_PREVIEW_PDF_CACHE_ENTRIES)
def _clip(text: str) -> Dict[str, Any]:
    return {"text": text[:FILE_PREVIEW_TEXT_CHARS], "truncated": len(text) > FILE_PREVIEW_TEXT_CHARS}
def text_preview(text: str) -> Dict[str, Any]:
    return {"type": "text", **_clip(text)}
def _decoded(data: bytes) -> str:
    try:
        text = decode_text(data)
    except ConversationFileError as e:
        raise ConversationFileError(UNSUPPORTED) from e
    if "\x00" in text:
        raise ConversationFileError(UNSUPPORTED)
    return text
def _open_pdf(data: bytes) -> pymupdf.Document:
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except RuntimeError as e:
        raise ConversationFileError("PDF 檔案損毀，無法預覽") from e
    if document.needs_pass:
        document.close()
        raise ConversationFileError("PDF 有密碼保護，無法預覽")
    return document
def render_pdf_page(data: bytes, page_number: int) -> bytes:
    with _open_pdf(data) as document:
        if not 1 <= page_number <= document.page_count:
            raise ConversationFileError("頁碼超出範圍")
        page = document[page_number - 1]
        zoom = min(FILE_PREVIEW_PAGE_DPI / 72, FILE_PREVIEW_PAGE_MAX_PIXELS / max(page.rect.width, page.rect.height, 1))
        return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")
def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (datetime, date, time)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    return str(value)
def _table_rows(rows: Iterator[List[str]]) -> Dict[str, Any]:
    kept: List[List[str]] = []
    truncated = False
    for row in rows:
        if len(kept) == FILE_PREVIEW_SHEET_ROWS:
            truncated = True
            break
        truncated = truncated or len(row) > FILE_PREVIEW_SHEET_COLUMNS
        kept.append(row[:FILE_PREVIEW_SHEET_COLUMNS])
    return {"rows": kept, "truncated": truncated}
def _trimmed(rows: List[List[str]]) -> List[List[str]]:
    while rows and not any(rows[-1]):
        rows.pop()
    width = max((max((index + 1 for index, value in enumerate(row) if value), default=0) for row in rows), default=0)
    return [row[:width] for row in rows]
def _runs(paragraph) -> List[Dict[str, Any]]:
    runs: List[Dict[str, Any]] = []
    for item in paragraph.iter_inner_content():
        bold, italic = (False, False) if isinstance(item, Hyperlink) else (bool(item.bold), bool(item.italic))
        if not item.text:
            continue
        if runs and (runs[-1]["bold"], runs[-1]["italic"]) == (bold, italic):
            runs[-1]["text"] += item.text
        else:
            runs.append({"text": item.text, "bold": bold, "italic": italic})
    return runs
def _style_number(style: str) -> Optional[int]:
    last = style.split()[-1] if style else ""
    return int(last) if last.isdigit() else None
def _paragraph_block(paragraph) -> Optional[Dict[str, Any]]:
    runs = _runs(paragraph)
    if not "".join(run["text"] for run in runs).strip():
        return None
    style = paragraph.style.name if paragraph.style is not None else ""
    if style == "Title" or style.startswith("Heading"):
        return {"type": "heading", "level": 1 if style == "Title" else min(_style_number(style) or 1, 6), "runs": runs}
    properties = paragraph._p.pPr
    numbering = properties.numPr if properties is not None else None
    if numbering is not None or style.startswith("List"):
        if numbering is not None and numbering.ilvl is not None:
            level = numbering.ilvl.val
        else:
            level = (_style_number(style) or 1) - 1
        return {"type": "list_item", "ordered": "Number" in style, "level": min(level, 8), "runs": runs}
    return {"type": "paragraph", "runs": runs}
def _docx_document(path: str) -> Dict[str, Any]:
    blocks: List[Dict[str, Any]] = []
    truncated = False
    for item in WordDocument(path).iter_inner_content():
        if len(blocks) == FILE_PREVIEW_ITEMS:
            truncated = True
            break
        if isinstance(item, Table):
            blocks.append({"type": "table", **_table_rows([cell.text for cell in row.cells] for row in item.rows)})
            continue
        block = _paragraph_block(item)
        if block is not None:
            blocks.append(block)
    return {"type": "document", "blocks": blocks, "truncated": truncated}
def _xlsx_sheets(path: str) -> Dict[str, Any]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = []
        for worksheet in workbook.worksheets:
            rows = worksheet.iter_rows(max_row=FILE_PREVIEW_SHEET_ROWS + 1, max_col=FILE_PREVIEW_SHEET_COLUMNS + 1, values_only=True)
            sheets.append({"name": worksheet.title, **_table_rows(_trimmed([[_cell_text(value) for value in row] for row in rows]))})
        return {"type": "sheets", "sheets": sheets}
    finally:
        workbook.close()
def _csv_sheets(filename: str, text: str) -> Dict[str, Any]:
    return {"type": "sheets", "sheets": [{"name": filename, **_table_rows(csv.reader(io.StringIO(text)))}]}
def _shapes(shapes) -> Iterator[Any]:
    for shape in shapes:
        if getattr(shape, "shapes", None) is not None:
            yield from _shapes(shape.shapes)
        else:
            yield shape
def _slide_items(slide, title_id: Optional[int]) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    images = 0
    for shape in _shapes(slide.shapes):
        if shape.shape_id == title_id:
            continue
        if isinstance(shape, Picture):
            images += 1
        if shape.has_text_frame:
            for paragraph in shape.text_frame.paragraphs:
                text = paragraph.text.strip()
                if text:
                    items.append({"type": "text", "level": paragraph.level, "text": text})
        if getattr(shape, "has_table", False) and shape.has_table:
            items.append({"type": "table", **_table_rows([cell.text for cell in row.cells] for row in shape.table.rows)})
    return {"items": items, "images": images}
def _pptx_slides(path: str) -> Dict[str, Any]:
    slides: List[Dict[str, Any]] = []
    total = 0
    truncated = False
    for number, slide in enumerate(Presentation(path).slides, start=1):
        if total >= FILE_PREVIEW_ITEMS:
            truncated = True
            break
        title = slide.shapes.title
        content = _slide_items(slide, title.shape_id if title is not None else None)
        total += len(content["items"]) + 1
        notes = slide.notes_slide.notes_text_frame.text.strip() if slide.has_notes_slide else ""
        slides.append({"number": number, "title": title.text.strip() if title is not None else "", "notes": notes, **content})
    return {"type": "slides", "slides": slides, "truncated": truncated}
def _preview(filename: str, data: bytes, limits: ExtractionLimits, allow_html: bool) -> Dict[str, Any]:
    extension = extension_of(filename)
    if extension == ".pdf":
        with _open_pdf(data) as document:
            return {"type": "pages", "page_count": document.page_count}
    if extension == ".docx":
        return with_checked_file(data, extension, limits, _docx_document)
    if extension == ".xlsx":
        return with_checked_file(data, extension, limits, _xlsx_sheets)
    if extension == ".pptx":
        return with_checked_file(data, extension, limits, _pptx_slides)
    if allow_html and extension in HTML_EXTENSIONS:
        return {"type": "html"}
    text = _decoded(data)
    if extension == ".csv":
        return _csv_sheets(filename, text)
    if extension in MARKDOWN_EXTENSIONS:
        return {"type": "markdown", **_clip(text)}
    return text_preview(text)
def build_preview(filename: str, data: bytes, limits: ExtractionLimits, allow_html: bool) -> Dict[str, Any]:
    try:
        return _preview(filename, data, limits, allow_html)
    except ConversationFileError as e:
        return {"type": "unsupported", "reason": str(e)}