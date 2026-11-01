import re
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Tuple, Union

from app.core.error_response import SafeClientError

Location = Tuple[Union[str, int], ...]
MAX_JSONPATH_CHARS = 2000
MAX_JSONPATH_NODES = 100_000
NOTHING = object()


class JsonPathError(SafeClientError):
    pass


@dataclass(frozen=True)
class Node:
    location: Location
    value: Any


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    pos: int


TOKEN_PATTERN = re.compile(
    r"""
    (?P<space>[ \t\n\r]+)
    |(?P<string>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
    |(?P<number>-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?)
    |(?P<op>\.\.|==|!=|<=|>=|&&|\|\||[$@.\[\]*,:?()!<>])
    |(?P<name>[A-Za-z_\u0080-\U0010FFFF][A-Za-z0-9_\u0080-\U0010FFFF]*)
    """,
    re.VERBOSE,
)


def _tokens(text: str) -> List[Token]:
    out: List[Token] = []
    pos = 0
    while pos < len(text):
        m = TOKEN_PATTERN.match(text, pos)
        if not m:
            raise JsonPathError(f"JSONPath 語法錯誤（位置 {pos}）：{text}")
        kind = m.lastgroup
        if kind != "space":
            out.append(Token(kind, m.group(kind), pos))
        elif out and out[-1].kind == "op" and out[-1].text in (".", ".."):
            raise JsonPathError(f"JSONPath 語法錯誤（位置 {pos}）：{text}")
        pos = m.end()
    out.append(Token("end", "", len(text)))
    return out


def _unquote(raw: str) -> str:
    body = raw[1:-1]
    out = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        nxt = body[i + 1]
        simple = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "/": "/", "\\": "\\", "'": "'", '"': '"'}
        if nxt in simple:
            out.append(simple[nxt])
            i += 2
        elif nxt == "u":
            code = int(body[i + 2:i + 6], 16)
            i += 6
            if 0xD800 <= code <= 0xDBFF and body[i:i + 2] == "\\u":
                low = int(body[i + 2:i + 6], 16)
                code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                i += 6
            out.append(chr(code))
        else:
            raise JsonPathError(f"JSONPath 字串含無效的跳脫字元：{raw}")
    return "".join(out)


class _Parser:
    FUNCTIONS = {"length": 1, "count": 1, "match": 2, "search": 2, "value": 1}

    def __init__(self, text: str):
        self.text = text
        self.tokens = _tokens(text)
        self.i = 0

    def peek(self, offset: int = 0) -> Token:
        return self.tokens[min(self.i + offset, len(self.tokens) - 1)]

    def take(self, text: Optional[str] = None, kind: Optional[str] = None) -> Token:
        tok = self.peek()
        if (text is not None and tok.text != text) or (kind is not None and tok.kind != kind):
            raise JsonPathError(f"JSONPath 語法錯誤（位置 {tok.pos}）：{self.text}")
        self.i += 1
        return tok

    def query(self) -> Tuple:
        self.take("$")
        segments = self.segments()
        self.take(kind="end")
        return ("query", "$", segments)

    def segments(self) -> List[Tuple]:
        segments = []
        while True:
            tok = self.peek()
            if tok.text == "..":
                self.i += 1
                segments.append(("descendant", self.segment_body(descendant=True)))
            elif tok.text == ".":
                self.i += 1
                segments.append(("child", self.dot_member()))
            elif tok.text == "[":
                segments.append(("child", self.bracket()))
            else:
                return segments

    def segment_body(self, descendant: bool) -> List[Tuple]:
        if self.peek().text == "[":
            return self.bracket()
        return self.dot_member()

    def dot_member(self) -> List[Tuple]:
        tok = self.peek()
        if tok.text == "*":
            self.i += 1
            return [("wildcard",)]
        if tok.kind == "name":
            self.i += 1
            return [("name", tok.text)]
        raise JsonPathError(f"JSONPath 語法錯誤（位置 {tok.pos}）：{self.text}")

    def bracket(self) -> List[Tuple]:
        self.take("[")
        selectors = [self.selector()]
        while self.peek().text == ",":
            self.i += 1
            selectors.append(self.selector())
        self.take("]")
        return selectors

    def _int(self, tok: Token) -> int:
        if not re.fullmatch(r"-?(0|[1-9][0-9]*)", tok.text) or tok.text == "-0":
            raise JsonPathError(f"JSONPath 索引必須是整數（位置 {tok.pos}）：{self.text}")
        value = int(tok.text)
        if abs(value) > 2 ** 53 - 1:
            raise JsonPathError(f"JSONPath 索引超出範圍：{tok.text}")
        return value

    def selector(self) -> Tuple:
        tok = self.peek()
        if tok.kind == "string":
            self.i += 1
            return ("name", _unquote(tok.text))
        if tok.text == "*":
            self.i += 1
            return ("wildcard",)
        if tok.text == "?":
            self.i += 1
            return ("filter", self.logical_or())
        if tok.kind == "number" or tok.text == ":":
            parts: List[Optional[int]] = [None, None, None]
            idx = 0
            saw_colon = False
            while True:
                t = self.peek()
                if t.kind == "number":
                    if parts[idx] is not None:
                        raise JsonPathError(f"JSONPath 索引必須是整數（位置 {t.pos}）：{self.text}")
                    parts[idx] = self._int(t)
                    self.i += 1
                elif t.text == ":":
                    saw_colon = True
                    idx += 1
                    if idx > 2:
                        raise JsonPathError(f"JSONPath 切片語法錯誤：{self.text}")
                    self.i += 1
                else:
                    break
            if not saw_colon:
                return ("index", parts[0])
            return ("slice", parts[0], parts[1], parts[2])
        raise JsonPathError(f"JSONPath 語法錯誤（位置 {tok.pos}）：{self.text}")

    def logical_or(self) -> Tuple:
        node = self.logical_and()
        while self.peek().text == "||":
            self.i += 1
            node = ("or", node, self.logical_and())
        return node

    def logical_and(self) -> Tuple:
        node = self.basic()
        while self.peek().text == "&&":
            self.i += 1
            node = ("and", node, self.basic())
        return node

    def basic(self) -> Tuple:
        tok = self.peek()
        if tok.text == "!":
            self.i += 1
            if self.peek().text == "(":
                self.i += 1
                inner = self.logical_or()
                self.take(")")
                return ("not", inner)
            return ("not", self.test_expr())
        if tok.text == "(":
            self.i += 1
            inner = self.logical_or()
            self.take(")")
            return inner
        left = self.comparable_or_test()
        op = self.peek().text
        if op in ("==", "!=", "<", "<=", ">", ">="):
            self.i += 1
            right = self.comparable_or_test()
            for side in (left, right):
                self._check_comparable(side)
            return ("cmp", op, left, right)
        if left[0] == "literal":
            raise JsonPathError(f"JSONPath 篩選式缺少比較運算子：{self.text}")
        if left[0] == "func" and left[1] in ("length", "value"):
            raise JsonPathError(f"JSONPath 函式 {left[1]}() 不能單獨當作條件：{self.text}")
        return ("test", left)

    def _check_comparable(self, side: Tuple) -> None:
        if side[0] == "query" and not self._singular(side):
            raise JsonPathError(f"JSONPath 比較式只能使用單一值查詢：{self.text}")
        if side[0] == "func" and side[1] in ("match", "search"):
            raise JsonPathError(f"JSONPath 函式 {side[1]}() 的結果不能比較：{self.text}")

    @staticmethod
    def _singular(query: Tuple) -> bool:
        return all(kind == "child" and len(sels) == 1 and sels[0][0] in ("name", "index") for kind, sels in query[2])

    def test_expr(self) -> Tuple:
        node = self.comparable_or_test()
        if node[0] == "literal":
            raise JsonPathError(f"JSONPath 篩選式語法錯誤：{self.text}")
        return ("test", node)

    def comparable_or_test(self) -> Tuple:
        tok = self.peek()
        if tok.text in ("$", "@"):
            self.i += 1
            return ("query", tok.text, self.segments())
        if tok.kind == "string":
            self.i += 1
            return ("literal", _unquote(tok.text))
        if tok.kind == "number":
            self.i += 1
            text = tok.text
            return ("literal", float(text) if any(c in text for c in ".eE") else int(text))
        if tok.kind == "name" and tok.text in ("true", "false", "null") and self.peek(1).text != "(":
            self.i += 1
            return ("literal", {"true": True, "false": False, "null": None}[tok.text])
        if tok.kind == "name" and self.peek(1).text == "(":
            name = tok.text
            if name not in self.FUNCTIONS:
                raise JsonPathError(f"JSONPath 不支援的函式 {name}()：{self.text}")
            self.i += 2
            args = [self.function_arg()]
            while self.peek().text == ",":
                self.i += 1
                args.append(self.function_arg())
            self.take(")")
            if len(args) != self.FUNCTIONS[name]:
                raise JsonPathError(f"JSONPath 函式 {name}() 的參數數量錯誤：{self.text}")
            return ("func", name, args)
        raise JsonPathError(f"JSONPath 語法錯誤（位置 {tok.pos}）：{self.text}")

    def function_arg(self) -> Tuple:
        tok = self.peek()
        if tok.text in ("!", "("):
            return self.logical_or()
        node = self.comparable_or_test()
        if self.peek().text in ("==", "!=", "<", "<=", ">", ">=", "&&", "||"):
            raise JsonPathError(f"JSONPath 函式參數不支援運算式：{self.text}")
        return node


def _normalize_index(index: int, length: int) -> int:
    return index + length if index < 0 else index


def _slice_indices(start, end, step, length) -> List[int]:
    step = 1 if step is None else step
    if step == 0:
        return []
    if step > 0:
        lower = 0 if start is None else _normalize_index(start, length)
        upper = length if end is None else _normalize_index(end, length)
        lower, upper = min(max(lower, 0), length), min(max(upper, 0), length)
        return list(range(lower, upper, step))
    upper = length - 1 if start is None else _normalize_index(start, length)
    lower = -1 if end is None else _normalize_index(end, length)
    upper, lower = min(max(upper, -1), length - 1), min(max(lower, -1), length - 1)
    return list(range(upper, lower, step))


def _iregexp(pattern: str) -> Optional[re.Pattern]:
    translated = []
    in_class = False
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\" and i + 1 < len(pattern):
            translated.append(pattern[i:i + 2])
            i += 2
            continue
        if ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        elif ch == "." and not in_class:
            translated.append("[^\\n\\r]")
            i += 1
            continue
        translated.append(ch)
        i += 1
    try:
        return re.compile("".join(translated))
    except re.error:
        return None


class _Evaluator:
    def __init__(self, root: Any):
        self.root = root
        self.visited = 0

    def run(self, query: Tuple, current: Node) -> List[Node]:
        start = Node((), self.root) if query[1] == "$" else current
        nodes = [start]
        for kind, selectors in query[2]:
            nodes = self.segment(nodes, kind, selectors)
        return nodes

    def _count(self, n: int) -> None:
        self.visited += n
        if self.visited > MAX_JSONPATH_NODES:
            raise JsonPathError("JSONPath 選取的節點數超過上限")

    def segment(self, nodes: List[Node], kind: str, selectors: List[Tuple]) -> List[Node]:
        out: List[Node] = []
        for node in nodes:
            targets = self.descendants(node) if kind == "descendant" else [node]
            for target in targets:
                for selector in selectors:
                    out.extend(self.select(target, selector))
        self._count(len(out))
        return out

    def descendants(self, node: Node) -> List[Node]:
        ordered: List[Node] = []
        stack = [node]
        while stack:
            current = stack.pop()
            ordered.append(current)
            children = self.children(current)
            self._count(len(children))
            stack.extend(reversed(children))
        return ordered

    @staticmethod
    def children(node: Node) -> List[Node]:
        value = node.value
        if isinstance(value, dict):
            return [Node(node.location + (k,), v) for k, v in value.items()]
        if isinstance(value, list):
            return [Node(node.location + (i,), v) for i, v in enumerate(value)]
        return []

    def select(self, node: Node, selector: Tuple) -> List[Node]:
        value = node.value
        kind = selector[0]
        if kind == "name":
            if isinstance(value, dict) and selector[1] in value:
                return [Node(node.location + (selector[1],), value[selector[1]])]
            return []
        if kind == "wildcard":
            return self.children(node)
        if kind == "index":
            if isinstance(value, list):
                index = _normalize_index(selector[1], len(value))
                if 0 <= index < len(value):
                    return [Node(node.location + (index,), value[index])]
            return []
        if kind == "slice":
            if isinstance(value, list):
                return [Node(node.location + (i,), value[i]) for i in _slice_indices(selector[1], selector[2], selector[3], len(value))]
            return []
        if kind == "filter":
            return [child for child in self.children(node) if self.truthy(selector[1], child)]
        return []

    def truthy(self, expr: Tuple, current: Node) -> bool:
        kind = expr[0]
        if kind == "or":
            return self.truthy(expr[1], current) or self.truthy(expr[2], current)
        if kind == "and":
            return self.truthy(expr[1], current) and self.truthy(expr[2], current)
        if kind == "not":
            return not self.truthy(expr[1], current)
        if kind == "cmp":
            return self.compare(expr[1], self.value_of(expr[2], current), self.value_of(expr[3], current))
        if kind == "test":
            inner = expr[1]
            if inner[0] == "query":
                return len(self.run(inner, current)) > 0
            result = self.function(inner, current)
            return result is True or (isinstance(result, list) and len(result) > 0)
        return False

    def value_of(self, expr: Tuple, current: Node) -> Any:
        if expr[0] == "literal":
            return expr[1]
        if expr[0] == "query":
            nodes = self.run(expr, current)
            return nodes[0].value if len(nodes) == 1 else NOTHING
        if expr[0] == "func":
            result = self.function(expr, current)
            return NOTHING if isinstance(result, list) else result
        return NOTHING

    def function(self, expr: Tuple, current: Node) -> Any:
        name, args = expr[1], expr[2]
        if name == "count":
            arg = args[0]
            return len(self.run(arg, current)) if arg[0] == "query" else NOTHING
        if name == "value":
            arg = args[0]
            nodes = self.run(arg, current) if arg[0] == "query" else []
            return nodes[0].value if len(nodes) == 1 else NOTHING
        if name == "length":
            value = self.value_of(args[0], current)
            if isinstance(value, str):
                return len(value)
            if isinstance(value, (list, dict)):
                return len(value)
            return NOTHING
        value = self.value_of(args[0], current)
        pattern = self.value_of(args[1], current)
        if not isinstance(value, str) or not isinstance(pattern, str):
            return False
        compiled = _iregexp(pattern)
        if compiled is None:
            return False
        return bool(compiled.fullmatch(value) if name == "match" else compiled.search(value))

    @staticmethod
    def _same(a: Any, b: Any) -> bool:
        if a is NOTHING or b is NOTHING:
            return a is NOTHING and b is NOTHING
        if isinstance(a, bool) or isinstance(b, bool):
            return isinstance(a, bool) and isinstance(b, bool) and a == b
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a == b
        if type(a) is not type(b):
            return False
        if isinstance(a, list):
            return len(a) == len(b) and all(_Evaluator._same(x, y) for x, y in zip(a, b))
        if isinstance(a, dict):
            return a.keys() == b.keys() and all(_Evaluator._same(a[k], b[k]) for k in a)
        return a == b

    def compare(self, op: str, a: Any, b: Any) -> bool:
        if op == "==":
            return self._same(a, b)
        if op == "!=":
            return not self._same(a, b)
        if op in ("<=", ">="):
            return self._same(a, b) or self.compare(op[0], a, b)
        if a is NOTHING or b is NOTHING or isinstance(a, bool) or isinstance(b, bool):
            return False
        numeric = isinstance(a, (int, float)) and isinstance(b, (int, float))
        if not numeric and not (isinstance(a, str) and isinstance(b, str)):
            return False
        return a < b if op == "<" else a > b


def compile_query(path: str) -> Tuple:
    if len(path) > MAX_JSONPATH_CHARS:
        raise JsonPathError("JSONPath 運算式過長")
    return _Parser(path).query()


def query(document: Any, path: str) -> List[Node]:
    return _Evaluator(document).run(compile_query(path), Node((), document))


def values(document: Any, path: str) -> List[Any]:
    return [node.value for node in query(document, path)]
