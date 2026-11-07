import pytest
from app.services.jsonpath import JsonPathError, query, values
STORE = {
    "store": {
        "book": [
            {"category": "reference", "author": "Nigel Rees", "title": "Sayings of the Century", "price": 8.95},
            {"category": "fiction", "author": "Evelyn Waugh", "title": "Sword of Honour", "price": 12.99},
            {"category": "fiction", "author": "Herman Melville", "title": "Moby Dick", "isbn": "0-553-21311-3", "price": 8.99},
            {"category": "fiction", "author": "J. R. R. Tolkien", "title": "The Lord of the Rings", "isbn": "0-395-19395-8", "price": 22.99},
        ],
        "bicycle": {"color": "red", "price": 399},
    }
}
FILTER_DOC = {
    "a": [3, 5, 1, 2, 4, 6, {"b": "j"}, {"b": "k"}, {"b": {}}, {"b": "kilo"}],
    "o": {"p": 1, "q": 2, "r": 3, "s": 5, "t": {"u": 6}},
    "e": "f",
}
AUTHORS = ["Nigel Rees", "Evelyn Waugh", "Herman Melville", "J. R. R. Tolkien"]
@pytest.mark.parametrize("path, expected", [
    ("$.store.book[*].author", AUTHORS),
    ("$..author", AUTHORS),
    ("$.store..price", [8.95, 12.99, 8.99, 22.99, 399]),
    ("$..book[2].author", ["Herman Melville"]),
    ("$..book[2].publisher", []),
    ("$..book[-1].title", ["The Lord of the Rings"]),
    ("$..book[0,1].title", ["Sayings of the Century", "Sword of Honour"]),
    ("$..book[:2].title", ["Sayings of the Century", "Sword of Honour"]),
    ("$..book[?@.isbn].title", ["Moby Dick", "The Lord of the Rings"]),
    ("$..book[?@.price<10].title", ["Sayings of the Century", "Moby Dick"]),
    ("$.store['bicycle'].color", ["red"]),
])
def test_rfc9535_bookstore_examples(path, expected):
    assert values(STORE, path) == expected
@pytest.mark.parametrize("path, expected", [
    ("$.a[?@.b == 'kilo']", [{"b": "kilo"}]),
    ("$.a[?(@.b == 'kilo')]", [{"b": "kilo"}]),
    ("$.a[?@>3.5]", [5, 4, 6]),
    ("$.a[?@.b]", [{"b": "j"}, {"b": "k"}, {"b": {}}, {"b": "kilo"}]),
    ("$.o[?@<3, ?@<3]", [1, 2, 1, 2]),
    ("$.a[?@<2 || @.b == \"k\"]", [1, {"b": "k"}]),
    ("$.a[?match(@.b, \"[jk]\")]", [{"b": "j"}, {"b": "k"}]),
    ("$.a[?search(@.b, \"[jk]\")]", [{"b": "j"}, {"b": "k"}, {"b": "kilo"}]),
    ("$.o[?@>1 && @<4]", [2, 3]),
    ("$.o[?@.u || @.x]", [{"u": 6}]),
    ("$.a[?@.b == $.x]", [3, 5, 1, 2, 4, 6]),
    ("$.a[?@ == @]", FILTER_DOC["a"]),
    ("$[?length(@) >= 5]", [FILTER_DOC["a"], FILTER_DOC["o"]]),
    ("$[?count(@.*) == 5]", [FILTER_DOC["o"]]),
    ("$.a[?!@.b]", [3, 5, 1, 2, 4, 6]),
])
def test_rfc9535_filter_examples(path, expected):
    assert values(FILTER_DOC, path) == expected
@pytest.mark.parametrize("path, expected", [
    ("$[1:3]", ["b", "c"]),
    ("$[5:]", ["f", "g"]),
    ("$[1:5:2]", ["b", "d"]),
    ("$[5:1:-2]", ["f", "d"]),
    ("$[::-1]", ["g", "f", "e", "d", "c", "b", "a"]),
    ("$[-2]", ["f"]),
    ("$[9]", []),
])
def test_rfc9535_slice_examples(path, expected):
    assert values(list("abcdefg"), path) == expected
def test_nodes_carry_their_location_for_updates():
    nodes = query(STORE, "$.store.book[?@.price > 20]")
    assert [n.location for n in nodes] == [("store", "book", 3)]
@pytest.mark.parametrize("path", ["store", "$.store.", "$[?@.price < ]", "$[?length(@.a)]", "$[01]", "$.a[?@.*  == 1]", "$[?foo(@)]"])
def test_invalid_queries_are_rejected(path):
    with pytest.raises(JsonPathError):
        query(STORE, path)