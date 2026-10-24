import csv
import json
import os
from typing import Any, Callable, List, Optional, Sequence

import yaml

from .models import (
    KIND_CSV,
    KIND_JSON,
    KIND_JSONL,
    KIND_XLSX,
    KIND_YAML,
    WARNING_OVER_LIMIT,
    WARNING_PARSE_FAILED,
    ExtractionResult,
    StructuredDataError,
    StructuredRecord,
    plain_result,
)
from .noise import clean_noise, find_declared_json
from .render import render_records
from .tabular import records_from_csv, records_from_xlsx
from .tree import records_from_tree

JSON_EXTENSIONS = frozenset({".json"})
JSONL_EXTENSIONS = frozenset({".jsonl"})
YAML_EXTENSIONS = frozenset({".yaml", ".yml"})
DECLARATION_EXTENSIONS = frozenset({".js", ".ts", ".jsx", ".tsx"})
TREE_TEXT_EXTENSIONS = JSON_EXTENSIONS | JSONL_EXTENSIONS | YAML_EXTENSIONS | DECLARATION_EXTENSIONS
DATA_FORMAT_EXTENSIONS = JSON_EXTENSIONS | JSONL_EXTENSIONS | YAML_EXTENSIONS | frozenset({".csv", ".xlsx"})
BOM = "﻿"


def is_data_format(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in DATA_FORMAT_EXTENSIONS


def _structured_result(records: List[StructuredRecord], kind: str) -> ExtractionResult:
    return ExtractionResult(
        text=render_records(records),
        kind=kind,
        records=tuple(records),
        structured_format=True,
        warning=None,
    )


def _parse_jsonl(text: str) -> List[Any]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _parse_yaml(text: str) -> Any:
    documents = list(yaml.safe_load_all(text))
    return documents[0] if len(documents) == 1 else documents


def _parse_tree(ext: str, text: str):
    body = text.lstrip(BOM)
    if ext in JSON_EXTENSIONS:
        return json.loads(body), KIND_JSON
    if ext in JSONL_EXTENSIONS:
        return _parse_jsonl(body), KIND_JSONL
    return _parse_yaml(body), KIND_YAML


def extract_tree_text(
    ext: str,
    raw_text: str,
    max_parse_chars: Optional[int],
    label_fields: Sequence[str],
    ignore_fields: Sequence[str],
) -> ExtractionResult:
    fallback_text = clean_noise(raw_text)
    if ext in DECLARATION_EXTENSIONS:
        body = find_declared_json(raw_text)
        if body is None or (max_parse_chars is not None and len(body) > max_parse_chars):
            return plain_result(fallback_text, False, None)
        try:
            root, kind = json.loads(body), KIND_JSON
        except (ValueError, RecursionError):
            return plain_result(fallback_text, False, None)
        structured_format = False
    else:
        if max_parse_chars is not None and len(raw_text) > max_parse_chars:
            return plain_result(fallback_text, True, WARNING_OVER_LIMIT)
        try:
            root, kind = _parse_tree(ext, raw_text)
        except (ValueError, RecursionError, yaml.YAMLError):
            return plain_result(fallback_text, True, WARNING_PARSE_FAILED)
        structured_format = True
    try:
        records = records_from_tree(root, label_fields, ignore_fields, len(raw_text))
    except (StructuredDataError, RecursionError):
        return plain_result(fallback_text, structured_format, WARNING_PARSE_FAILED)
    if not records:
        return plain_result(fallback_text, structured_format, None)
    return _structured_result(records, kind)


def extract_csv(
    file_path: str,
    label_fields: Sequence[str],
    plain_text: Callable[[], str],
    raw_text: Callable[[], str],
) -> ExtractionResult:
    try:
        records = records_from_csv(file_path, label_fields)
    except (csv.Error, UnicodeDecodeError):
        return plain_result(raw_text(), True, WARNING_PARSE_FAILED)
    if not records:
        return plain_result(plain_text(), True, None)
    return _structured_result(records, KIND_CSV)


def extract_xlsx(file_path: str, label_fields: Sequence[str], plain_text: Callable[[], str]) -> ExtractionResult:
    records = records_from_xlsx(file_path, label_fields)
    if not records:
        return plain_result(plain_text(), True, None)
    return _structured_result(records, KIND_XLSX)
