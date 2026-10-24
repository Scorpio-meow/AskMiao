import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .models import StructuredRecord

RECORD_SEPARATOR = "\n\n---\n\n"
CONTEXT_HEADER = "【上下文】"
RENDERED_HEADER_PATTERN = re.compile(r"【(?:上下文|(?:[^】\n]+ )?(?:記錄 \d+|第 \d+ 列))】")
PART_SUFFIX_PATTERN = re.compile(r"（\d+/\d+）$")
PIECE_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "：", "，", ". ", "! ", "? ", ", ", " ", ""]


def array_header(position: int, group: Optional[str]) -> str:
    return f"【{group} 記錄 {position}】" if group else f"【記錄 {position}】"


def row_header(row: int, sheet: Optional[str]) -> str:
    return f"【{sheet} 第 {row} 列】" if sheet else f"【第 {row} 列】"


def field_line(path: Optional[str], value: str) -> str:
    return f"{path}: {value}" if path else value


def header_line(record: StructuredRecord, part: int, part_count: int) -> str:
    line = record.header + (record.label or "")
    if part_count > 1:
        line += f"（{part}/{part_count}）"
    return line


def render_record(record: StructuredRecord) -> str:
    return "\n".join([header_line(record, 1, 1), *(field_line(path, value) for path, value in record.fields)])


def render_records(records: Sequence[StructuredRecord]) -> str:
    return RECORD_SEPARATOR.join(render_record(record) for record in records)


def count_rendered_records(text: str) -> int:
    count = 0
    for block in text.split(RECORD_SEPARATOR):
        first_line = block.lstrip().split("\n", 1)[0]
        if RENDERED_HEADER_PATTERN.match(first_line):
            count += 1
    return count


def _pack(units: List[str], budget: int) -> List[List[str]]:
    parts: List[List[str]] = []
    current: List[str] = []
    size = 0
    for unit in units:
        added = len(unit) + (1 if current else 0)
        if current and size + added > budget:
            parts.append(current)
            current = [unit]
            size = len(unit)
        else:
            current.append(unit)
            size += added
    if current:
        parts.append(current)
    return parts


def split_record(record: StructuredRecord, chunk_size: int) -> List[str]:
    whole = render_record(record)
    if len(whole) <= chunk_size:
        return [whole]
    lines = [field_line(path, value) for path, value in record.fields]
    base_header = len(record.header + (record.label or ""))
    digits = 1
    while True:
        budget = chunk_size - base_header - len(f"（{'9' * digits}/{'9' * digits}）") - 1
        if budget < 1:
            raise ValueError("CHUNK_SIZE 太小，容納不下結構化記錄的標頭")
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=budget,
            chunk_overlap=0,
            separators=PIECE_SEPARATORS,
            keep_separator="end",
            length_function=len,
        )
        units: List[str] = []
        for line in lines:
            units.extend([line] if len(line) <= budget else splitter.split_text(line))
        parts = _pack(units, budget)
        if len(str(len(parts))) <= digits:
            break
        digits = len(str(len(parts)))
    total = len(parts)
    return [header_line(record, index, total) + "\n" + "\n".join(part) for index, part in enumerate(parts, start=1)]


def record_metadata(record: StructuredRecord, part: int, part_count: int) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "record_index": record.record_index,
        "part": part,
        "part_count": part_count,
        "preserve_whole": True,
    }
    if record.label is not None:
        metadata["label"] = record.label
    if record.links:
        metadata["links"] = list(record.links)
    if record.group is not None:
        metadata["group"] = record.group
    if record.sheet is not None:
        metadata["sheet"] = record.sheet
    if record.row is not None:
        metadata["row"] = record.row
    return metadata


def record_chunks(record: StructuredRecord, chunk_size: int) -> List[Tuple[str, Dict[str, Any]]]:
    texts = split_record(record, chunk_size)
    return [(text, record_metadata(record, index, len(texts))) for index, text in enumerate(texts, start=1)]


def merge_record_parts(texts: Sequence[str]) -> str:
    first_line, _, first_body = texts[0].partition("\n")
    merged = [PART_SUFFIX_PATTERN.sub("", first_line)]
    if first_body:
        merged.append(first_body)
    for text in texts[1:]:
        _, _, body = text.partition("\n")
        if body:
            merged.append(body)
    return "\n".join(merged)
