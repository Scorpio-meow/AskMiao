import asyncio
import csv
import io
import json
import os
import re
import tempfile
from typing import Any, Callable, Dict, Iterator, List, Optional
import pymupdf
from docx import Document as WordDocument
from docx.shared import Pt
from markdown_it import MarkdownIt
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from pptx import Presentation
from pptx.util import Inches
from app.core.limits import (
    CHAT_ATTACHMENT_EXTRACTION_LIMITS,
    FILE_READ_PAGE_CHARS,
    MAX_FILE_EDITS,
    MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS,
    MAX_FILE_TOOL_CONTENT_CHARS,
    MAX_GENERATED_PDF_PAGES,
    MAX_PRESENTATION_SLIDES,
    MAX_SPREADSHEET_CELLS,
)
from app.services.conversation_files import ConversationFileError, extension_of
from app.services.document_processor import DocumentProcessor, DocumentRejected
CREATABLE_EXTENSIONS = (".md", ".txt", ".csv", ".json", ".docx", ".xlsx", ".pptx", ".pdf")
TEXT_EXTENSIONS = (".md", ".txt", ".csv", ".json", ".html", ".htm", ".css", ".js", ".ts", ".py")
TEXT_ENCODINGS = ("utf-8-sig", "big5", "gbk", "gb2312")
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
CELL_ADDRESS = re.compile(r"^[A-Z]{1,3}[1-9][0-9]{0,6}$")
CODE_FONT = "Consolas"
PDF_MARGIN = 56
PDF_CSS = (
    "* { font-family: sans-serif; font-size: 11pt; line-height: 1.5; }"
    "h1 { font-size: 20pt; } h2 { font-size: 16pt; } h3 { font-size: 13pt; }"
    "table { border-collapse: collapse; margin: 6pt 0; }"
    "th, td { border: 0.5pt solid #888888; padding: 3pt 6pt; } th { background: #f0f0f0; }"
    "code, pre { font-family: monospace; font-size: 9.5pt; } pre { background: #f6f6f6; padding: 6pt; }"
    "blockquote { color: #555555; margin-left: 12pt; }"
)
extraction_slots = asyncio.Semaphore(MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS)
markdown = MarkdownIt("commonmark", {"html": False}).enable("table")
def _text_field(payload: Dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ConversationFileError(f"這個格式需要字串欄位 {key}")
    if len(value) > MAX_FILE_TOOL_CONTENT_CHARS:
        raise ConversationFileError(f"{key} 不可超過 {MAX_FILE_TOOL_CONTENT_CHARS} 字元")
    return value
def _cell_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return json.dumps(value, ensure_ascii=False)
def _sheets_field(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    sheets = payload.get("sheets")
    if not isinstance(sheets, list) or not sheets:
        raise ConversationFileError("這個格式需要 sheets：[{name, rows}]，至少一張工作表")
    cells = 0
    names = set()
    parsed = []
    for sheet in sheets:
        if not isinstance(sheet, dict) or not isinstance(sheet.get("name"), str) or not isinstance(sheet.get("rows"), list):
            raise ConversationFileError("每張工作表都需要字串 name 與陣列 rows")
        name = sheet["name"].strip()
        if not name or name in names:
            raise ConversationFileError(f"工作表名稱不可空白或重複：{name}")
        names.add(name)
        rows = []
        for row in sheet["rows"]:
            if not isinstance(row, list):
                raise ConversationFileError("rows 的每一列都必須是陣列")
            cells += len(row)
            rows.append([_cell_value(value) for value in row])
        if cells > MAX_SPREADSHEET_CELLS:
            raise ConversationFileError(f"儲存格總數不可超過 {MAX_SPREADSHEET_CELLS}")
        parsed.append({"name": name, "rows": rows})
    return parsed
def _slides_field(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    slides = payload.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ConversationFileError("這個格式需要 slides：[{title, bullets, notes}]，至少一頁")
    if len(slides) > MAX_PRESENTATION_SLIDES:
        raise ConversationFileError(f"簡報不可超過 {MAX_PRESENTATION_SLIDES} 頁")
    parsed = []
    for slide in slides:
        if not isinstance(slide, dict) or not isinstance(slide.get("title"), str):
            raise ConversationFileError("每一頁都需要字串 title")
        bullets = slide.get("bullets") or []
        notes = slide.get("notes") or ""
        if not isinstance(bullets, list) or not all(isinstance(item, str) for item in bullets) or not isinstance(notes, str):
            raise ConversationFileError("bullets 必須是字串陣列，notes 必須是字串")
        parsed.append({"title": slide["title"], "bullets": bullets, "notes": notes})
    if sum(len(s["title"]) + len(s["notes"]) + sum(map(len, s["bullets"])) for s in parsed) > MAX_FILE_TOOL_CONTENT_CHARS:
        raise ConversationFileError(f"簡報文字不可超過 {MAX_FILE_TOOL_CONTENT_CHARS} 字元")
    return parsed
def _set_cell(cell, value: Any) -> None:
    cell.value = value
    if isinstance(value, str):
        cell.data_type = "s"
def _safe_csv_value(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value
def _build_csv(sheets: List[Dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in sheets[0]["rows"]:
        writer.writerow(["" if value is None else _safe_csv_value(value) for value in row])
    return buffer.getvalue().encode("utf-8-sig")
def _build_xlsx(sheets: List[Dict[str, Any]]) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet in sheets:
        try:
            worksheet = workbook.create_sheet(title=sheet["name"])
        except ValueError as e:
            raise ConversationFileError(f"工作表名稱無效：{sheet['name']}") from e
        for row_index, row in enumerate(sheet["rows"], start=1):
            for column_index, value in enumerate(row, start=1):
                _set_cell(worksheet.cell(row=row_index, column=column_index), value)
        if sheet["rows"]:
            for cell in worksheet[1]:
                cell.font = Font(bold=True)
            worksheet.freeze_panes = "A2"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
def _add_inline(paragraph, inline, bold: bool) -> None:
    state = {"bold": bold, "italic": False}
    for child in inline.children or []:
        if child.type == "strong_open":
            state["bold"] = True
        elif child.type == "strong_close":
            state["bold"] = bold
        elif child.type == "em_open":
            state["italic"] = True
        elif child.type == "em_close":
            state["italic"] = False
        elif child.type in ("softbreak", "hardbreak"):
            paragraph.add_run().add_break()
        elif child.type in ("text", "code_inline", "image"):
            run = paragraph.add_run(child.content)
            run.bold = state["bold"]
            run.italic = state["italic"]
            if child.type == "code_inline":
                run.font.name = CODE_FONT
def _add_table(document, tokens, start: int) -> int:
    rows: List[List[Any]] = []
    index = start
    while tokens[index].type != "table_close":
        token = tokens[index]
        if token.type == "tr_open":
            rows.append([])
        elif token.type == "inline" and rows:
            rows[-1].append(token)
        index += 1
    columns = max((len(row) for row in rows), default=0)
    if columns:
        table = document.add_table(rows=len(rows), cols=columns, style="Table Grid")
        for row_index, row in enumerate(rows):
            for column_index, inline in enumerate(row):
                _add_inline(table.cell(row_index, column_index).paragraphs[0], inline, bold=row_index == 0)
    return index + 1
def _build_docx(content: str) -> bytes:
    document = WordDocument()
    tokens = markdown.parse(content)
    lists: List[str] = []
    quotes = 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == "heading_open":
            _add_inline(document.add_heading(level=min(int(token.tag[1]), 9)), tokens[index + 1], bold=False)
            index += 3
            continue
        if token.type == "paragraph_open":
            if lists:
                style = "List Number" if lists[-1] == "ordered" else "List Bullet"
                style = style if len(lists) == 1 else f"{style} {min(len(lists), 3)}"
            else:
                style = "Quote" if quotes else None
            _add_inline(document.add_paragraph(style=style), tokens[index + 1], bold=False)
            index += 3
            continue
        if token.type == "table_open":
            index = _add_table(document, tokens, index)
            continue
        if token.type in ("bullet_list_open", "ordered_list_open"):
            lists.append("ordered" if token.type == "ordered_list_open" else "bullet")
        elif token.type in ("bullet_list_close", "ordered_list_close"):
            lists.pop()
        elif token.type == "blockquote_open":
            quotes += 1
        elif token.type == "blockquote_close":
            quotes -= 1
        elif token.type in ("fence", "code_block"):
            run = document.add_paragraph().add_run(token.content.rstrip("\n"))
            run.font.name = CODE_FONT
            run.font.size = Pt(9.5)
        index += 1
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
def _build_pdf(content: str) -> bytes:
    story = pymupdf.Story(html=markdown.render(content), user_css=PDF_CSS)
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    mediabox = pymupdf.paper_rect("a4")
    area = mediabox + (PDF_MARGIN, PDF_MARGIN, -PDF_MARGIN, -PDF_MARGIN)
    more = True
    pages = 0
    while more:
        pages += 1
        if pages > MAX_GENERATED_PDF_PAGES:
            writer.close()
            raise ConversationFileError(f"PDF 不可超過 {MAX_GENERATED_PDF_PAGES} 頁")
        device = writer.begin_page(mediabox)
        more, _ = story.place(area)
        story.draw(device)
        writer.end_page()
    writer.close()
    with pymupdf.open("pdf", buffer.getvalue()) as document:
        document.subset_fonts()
        return document.tobytes(garbage=3, deflate=True)
def _build_pptx(slides: List[Dict[str, Any]]) -> bytes:
    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)
    layout = presentation.slide_layouts[1]
    for spec in slides:
        slide = presentation.slides.add_slide(layout)
        slide.shapes.title.text = spec["title"]
        body = slide.placeholders[1].text_frame
        body.clear()
        for position, bullet in enumerate(spec["bullets"]):
            paragraph = body.paragraphs[0] if position == 0 else body.add_paragraph()
            paragraph.text = bullet
        if spec["notes"]:
            slide.notes_slide.notes_text_frame.text = spec["notes"]
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()
def build_file(extension: str, payload: Dict[str, Any]) -> bytes:
    if extension in (".md", ".txt"):
        return _text_field(payload, "content").encode("utf-8")
    if extension == ".json":
        content = _text_field(payload, "content")
        try:
            json.loads(content)
        except ValueError as e:
            raise ConversationFileError(f"content 不是有效的 JSON：{e}") from e
        return content.encode("utf-8")
    if extension == ".csv":
        return _build_csv(_sheets_field(payload))
    if extension == ".xlsx":
        return _build_xlsx(_sheets_field(payload))
    if extension == ".docx":
        return _build_docx(_text_field(payload, "content"))
    if extension == ".pdf":
        return _build_pdf(_text_field(payload, "content"))
    if extension == ".pptx":
        return _build_pptx(_slides_field(payload))
    raise ConversationFileError(f"只能建立這些格式：{'、'.join(CREATABLE_EXTENSIONS)}")
def decode_text(data: bytes) -> str:
    for encoding in TEXT_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ConversationFileError("無法辨識這個檔案的文字編碼")
def _with_checked_file(data: bytes, extension: str, use: Callable[[str], Any]) -> Any:
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, f"file{extension}")
        with open(path, "wb") as handle:
            handle.write(data)
        if extension in (".docx", ".xlsx", ".pptx"):
            try:
                DocumentProcessor._check_ooxml_archive(path, CHAT_ATTACHMENT_EXTRACTION_LIMITS, builds_dom=True)
            except DocumentRejected as e:
                raise ConversationFileError(e.reason) from e
        return use(path)
def _xlsx_text(path: str) -> str:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        lines = []
        for worksheet in workbook.worksheets:
            lines.append(f"## 工作表：{worksheet.title}")
            for row in worksheet.iter_rows():
                cells = [f"{cell.coordinate}: {cell.value}" for cell in row if getattr(cell, "coordinate", None) and cell.value is not None]
                if cells:
                    lines.append(" | ".join(cells))
        return "\n".join(lines)
    finally:
        workbook.close()
def _extracted_text(path: str) -> str:
    try:
        return DocumentProcessor.extract_document(path, "", CHAT_ATTACHMENT_EXTRACTION_LIMITS, None).text or ""
    except DocumentRejected as e:
        raise ConversationFileError(e.reason) from e
    except ValueError as e:
        raise ConversationFileError("無法讀取這個檔案的內容") from e
def file_text(filename: str, data: bytes) -> str:
    extension = extension_of(filename)
    if extension in TEXT_EXTENSIONS:
        return decode_text(data)
    if extension == ".xlsx":
        return _with_checked_file(data, extension, _xlsx_text)
    return _with_checked_file(data, extension, _extracted_text)
def read_page(text: str, offset: int) -> Dict[str, Any]:
    start = max(0, min(offset, len(text)))
    end = min(len(text), start + FILE_READ_PAGE_CHARS)
    return {
        "content": text[start:end],
        "offset": start,
        "next_offset": end if end < len(text) else None,
        "total_chars": len(text),
    }
def _edits_field(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    edits = payload.get("edits")
    if not isinstance(edits, list) or not edits or len(edits) > MAX_FILE_EDITS:
        raise ConversationFileError(f"edits 必須是 1 到 {MAX_FILE_EDITS} 個 {{find, replace}}")
    for edit in edits:
        if not isinstance(edit, dict) or not isinstance(edit.get("find"), str) or not edit["find"] or not isinstance(edit.get("replace"), str):
            raise ConversationFileError("每個修改都需要非空字串 find 與字串 replace")
    return edits
def _unique_match_error(position: int, find: str, count: int) -> ConversationFileError:
    where = "找不到" if count == 0 else f"出現 {count} 次"
    return ConversationFileError(f"第 {position} 個修改的 find「{find[:60]}」{where}；find 必須剛好出現一次，請加長前後文")
def _edit_text(text: str, edits: List[Dict[str, str]]) -> str:
    for position, edit in enumerate(edits, start=1):
        count = text.count(edit["find"])
        if count != 1:
            raise _unique_match_error(position, edit["find"], count)
        text = text.replace(edit["find"], edit["replace"], 1)
    return text
def _replace_in_paragraph(paragraph, find: str, replace: str) -> None:
    runs = paragraph.runs
    start = "".join(run.text for run in runs).find(find)
    if start < 0:
        raise ConversationFileError("要修改的文字位在無法編輯的區塊（例如超連結），請改用整份重寫")
    end = start + len(find)
    run_end = 0
    first = True
    for run in runs:
        text = run.text
        run_start, run_end = run_end, run_end + len(text)
        if run_end <= start or run_start >= end:
            continue
        head = text[:start - run_start] + replace if first else ""
        tail = text[end - run_start:] if end <= run_end else ""
        run.text = head + tail
        first = False
def _edit_paragraphs(paragraphs: List[Any], edits: List[Dict[str, str]]) -> None:
    for position, edit in enumerate(edits, start=1):
        matches = [(paragraph, paragraph.text.count(edit["find"])) for paragraph in paragraphs]
        total = sum(count for _, count in matches)
        if total != 1:
            raise _unique_match_error(position, edit["find"], total)
        paragraph = next(paragraph for paragraph, count in matches if count)
        _replace_in_paragraph(paragraph, edit["find"], edit["replace"])
def _docx_paragraphs(document) -> List[Any]:
    def from_container(container) -> Iterator[Any]:
        yield from container.paragraphs
        for table in container.tables:
            for row in table.rows:
                for cell in row.cells:
                    yield from from_container(cell)
    unique = {}
    for paragraph in from_container(document):
        unique.setdefault(id(paragraph._p), paragraph)
    return list(unique.values())
def _edit_docx(path: str, edits: List[Dict[str, str]]) -> bytes:
    document = WordDocument(path)
    _edit_paragraphs(_docx_paragraphs(document), edits)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
def _pptx_paragraphs(presentation) -> List[Any]:
    def from_shapes(shapes) -> Iterator[Any]:
        for shape in shapes:
            if getattr(shape, "shapes", None) is not None:
                yield from from_shapes(shape.shapes)
            if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                yield from shape.text_frame.paragraphs
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        yield from cell.text_frame.paragraphs
    return [paragraph for slide in presentation.slides for paragraph in from_shapes(slide.shapes)]
def _edit_pptx(path: str, edits: List[Dict[str, str]]) -> bytes:
    presentation = Presentation(path)
    _edit_paragraphs(_pptx_paragraphs(presentation), edits)
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()
def _cells_field(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    cells = payload.get("cells")
    if not isinstance(cells, list) or not cells or len(cells) > MAX_SPREADSHEET_CELLS:
        raise ConversationFileError("cells 必須是 [{sheet, cell, value}] 陣列")
    for item in cells:
        if not isinstance(item, dict) or not isinstance(item.get("sheet"), str) or not isinstance(item.get("cell"), str):
            raise ConversationFileError("每個儲存格修改都需要字串 sheet 與 cell，例如 {\"sheet\": \"工作表1\", \"cell\": \"B3\", \"value\": 120}")
        if not CELL_ADDRESS.match(item["cell"].strip().upper()):
            raise ConversationFileError(f"儲存格位址無效：{item['cell']}")
    return cells
def _edit_xlsx(path: str, cells: List[Dict[str, Any]]) -> bytes:
    workbook = load_workbook(path)
    for item in cells:
        if item["sheet"] not in workbook.sheetnames:
            raise ConversationFileError(f"找不到工作表「{item['sheet']}」，現有：{'、'.join(workbook.sheetnames)}")
        _set_cell(workbook[item["sheet"]][item["cell"].strip().upper()], _cell_value(item.get("value")))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
def edit_file(filename: str, data: bytes, payload: Dict[str, Any]) -> bytes:
    extension = extension_of(filename)
    rewrite = any(payload.get(key) is not None for key in ("content", "sheets", "slides"))
    if rewrite:
        if extension not in CREATABLE_EXTENSIONS:
            raise ConversationFileError(f"{extension} 無法整份重寫，請用 create_conversation_file 另存成 {'、'.join(CREATABLE_EXTENSIONS)} 其中一種格式")
        return build_file(extension, payload)
    if extension in TEXT_EXTENSIONS:
        return _edit_text(decode_text(data), _edits_field(payload)).encode("utf-8-sig" if extension == ".csv" else "utf-8")
    if extension == ".docx":
        edits = _edits_field(payload)
        return _with_checked_file(data, extension, lambda path: _edit_docx(path, edits))
    if extension == ".pptx":
        edits = _edits_field(payload)
        return _with_checked_file(data, extension, lambda path: _edit_pptx(path, edits))
    if extension == ".xlsx":
        cells = _cells_field(payload)
        return _with_checked_file(data, extension, lambda path: _edit_xlsx(path, cells))
    raise ConversationFileError(f"{extension} 只能讀取，不能部分修改；請改用 content／sheets／slides 整份重寫成新版本，或另存成其他格式")