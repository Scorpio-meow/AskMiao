from dataclasses import dataclass
from typing import Optional, Tuple

KIND_PLAIN = "plain"
KIND_JSON = "json"
KIND_JSONL = "jsonl"
KIND_YAML = "yaml"
KIND_CSV = "csv"
KIND_XLSX = "xlsx"

KIND_LABELS = {
    KIND_JSON: "JSON",
    KIND_JSONL: "JSONL",
    KIND_YAML: "YAML",
    KIND_CSV: "CSV",
    KIND_XLSX: "Excel",
}

WARNING_PARSE_FAILED = "結構化解析失敗，已改用純文字處理"
WARNING_OVER_LIMIT = "內容超過結構化解析上限，已改用純文字處理"


class StructuredDataError(ValueError):
    pass


@dataclass(frozen=True)
class StructuredRecord:
    record_index: int
    header: str
    label: Optional[str]
    fields: Tuple[Tuple[Optional[str], str], ...]
    links: Tuple[str, ...]
    group: Optional[str]
    sheet: Optional[str]
    row: Optional[int]


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    kind: str
    records: Tuple[StructuredRecord, ...]
    structured_format: bool
    warning: Optional[str]

    @property
    def field_names(self) -> Tuple[str, ...]:
        names = {}
        for record in self.records:
            for path, _ in record.fields:
                if path is None:
                    continue
                top = path.split(".", 1)[0].split("[", 1)[0]
                if top:
                    names.setdefault(top, None)
        return tuple(names)


def plain_result(text: str, structured_format: bool, warning: Optional[str]) -> ExtractionResult:
    return ExtractionResult(text=text, kind=KIND_PLAIN, records=(), structured_format=structured_format, warning=warning)
