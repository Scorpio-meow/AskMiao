import itertools
from typing import Any, Iterator, List, Optional, Sequence, Tuple

from .models import StructuredDataError, StructuredRecord
from .render import CONTEXT_HEADER, array_header
from .values import is_link, is_scalar, make_label, render_scalar, unique_links


class _TreeFlattener:
    def __init__(self, ignore_fields: Sequence[str], node_budget: int):
        self.ignore = {field.lower() for field in ignore_fields}
        self.node_budget = node_budget
        self.visited = 0

    def _visit(self, count: int) -> None:
        self.visited += count
        if self.visited > self.node_budget:
            raise StructuredDataError("結構化資料展開後的節點數超過原始文字長度")

    def is_ignored(self, key: Any) -> bool:
        return str(key).lower() in self.ignore

    def flatten(self, value: Any) -> Tuple[List[Tuple[Optional[str], str]], List[str]]:
        fields: List[Tuple[Optional[str], str]] = []
        links: List[str] = []
        self._walk(value, "", fields, links)
        return fields, links

    def _walk(self, value: Any, path: str, fields: list, links: list) -> None:
        self._visit(1)
        if isinstance(value, dict):
            for key, child in value.items():
                if self.is_ignored(key):
                    continue
                key_text = str(key)
                self._walk(child, f"{path}.{key_text}" if path else key_text, fields, links)
            return
        if isinstance(value, (list, tuple, set, frozenset)):
            items = list(value)
            if items and all(is_scalar(item) for item in items):
                self._visit(len(items))
                rendered = [text for text in (render_scalar(item) for item in items) if text]
                links.extend(text for text in rendered if is_link(text))
                if rendered:
                    fields.append((path or None, ", ".join(rendered)))
                return
            for index, item in enumerate(items):
                self._walk(item, f"{path}[{index}]", fields, links)
            return
        text = render_scalar(value)
        if text:
            if is_link(text):
                links.append(text)
            fields.append((path or None, text))


def _label_of(item: Any, label_fields: Sequence[str], flattener: _TreeFlattener) -> Optional[str]:
    if not isinstance(item, dict):
        return None
    for name in label_fields:
        if name in item and not flattener.is_ignored(name) and is_scalar(item[name]):
            label = make_label(render_scalar(item[name]))
            if label:
                return label
    return None


def _object_array_keys(root: dict, flattener: _TreeFlattener) -> List[Any]:
    return [
        key for key, value in root.items()
        if not flattener.is_ignored(key)
        and isinstance(value, list)
        and value
        and all(isinstance(element, dict) for element in value)
    ]


def _entries(root: Any, flattener: _TreeFlattener) -> Tuple[Optional[dict], Iterator[Tuple[Optional[str], int, Any]]]:
    if isinstance(root, list):
        return None, ((None, position, item) for position, item in enumerate(root, start=1))
    group_keys = _object_array_keys(root, flattener)
    if not group_keys:
        return None, iter([(None, 1, root)])
    context = {key: value for key, value in root.items() if key not in group_keys}
    return context, (
        (str(key), position, element)
        for key in group_keys
        for position, element in enumerate(root[key], start=1)
    )


def records_from_tree(
    root: Any,
    label_fields: Sequence[str],
    ignore_fields: Sequence[str],
    node_budget: int,
) -> List[StructuredRecord]:
    if not isinstance(root, (list, dict)):
        return []
    flattener = _TreeFlattener(ignore_fields, node_budget)
    counter = itertools.count(1)
    records: List[StructuredRecord] = []
    context, entries = _entries(root, flattener)
    if context:
        fields, links = flattener.flatten(context)
        if fields:
            records.append(StructuredRecord(
                record_index=next(counter),
                header=CONTEXT_HEADER,
                label=None,
                fields=tuple(fields),
                links=unique_links(links),
                group=None,
                sheet=None,
                row=None,
            ))
    for group, position, item in entries:
        fields, links = flattener.flatten(item)
        if not fields:
            continue
        records.append(StructuredRecord(
            record_index=next(counter),
            header=array_header(position, group),
            label=_label_of(item, label_fields, flattener),
            fields=tuple(fields),
            links=unique_links(links),
            group=group,
            sheet=None,
            row=None,
        ))
    return records
