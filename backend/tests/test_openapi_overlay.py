import json
import pytest
from app.core.error_response import SafeClientError
from app.services import openapi_documents
from app.services.openapi_overlay import apply_overlay
from app.services.openapi_parser import OpenApiParser
SPEC = {
    "openapi": "3.1.0",
    "info": {"title": "Pets", "version": "1"},
    "servers": [{"url": "https://api.example.com"}],
    "paths": {
        "/pets": {"get": {"operationId": "listPets", "tags": ["public"]}},
        "/internal/metrics": {"get": {"operationId": "metrics", "x-internal": True}},
        "/pets/{id}": {"delete": {"operationId": "deletePet", "x-internal": True}},
    },
}
def overlay(*actions, **extra):
    return {"overlay": "1.0.0", "info": {"title": "o", "version": "1"}, "actions": list(actions), **extra}
def test_update_merges_objects_and_appends_to_arrays():
    result = apply_overlay(SPEC, overlay(
        {"target": "$.info", "update": {"description": "公開版"}},
        {"target": "$.paths['/pets'].get.tags", "update": "pets"},
        {"target": "$.paths['/pets'].get", "update": {"tags": ["extra"], "summary": "列出寵物"}},
    ))
    assert result["info"] == {"title": "Pets", "version": "1", "description": "公開版"}
    assert result["paths"]["/pets"]["get"]["tags"] == ["public", "pets", "extra"]
    assert result["paths"]["/pets"]["get"]["summary"] == "列出寵物"
    assert SPEC["info"] == {"title": "Pets", "version": "1"}
def test_remove_with_filter_and_zero_matches_is_fine():
    result = apply_overlay(SPEC, overlay(
        {"target": "$.paths.*[?@['x-internal'] == true]", "remove": True},
        {"target": "$.paths['/missing']", "remove": True},
    ))
    assert result["paths"]["/pets"]["get"]["operationId"] == "listPets"
    assert result["paths"]["/internal/metrics"] == {}
    assert result["paths"]["/pets/{id}"] == {}
def test_copy_and_reusable_actions_from_overlay_1_1():
    doc = {**SPEC, "components": {"schemas": {}}, "paths": {"/a": {"get": {"summary": "A"}}}}
    result = apply_overlay(doc, {
        "overlay": "1.1.0",
        "info": {"title": "o", "version": "1"},
        "components": {"actions": {"describe": {"target": "$.info", "update": {"description": "共用"}}}},
        "actions": [
            {"$ref": "#/components/actions/describe"},
            {"target": "$.paths", "update": {"/b": {}}},
            {"target": "$.paths['/b']", "copy": "$.paths['/a']"},
        ],
    })
    assert result["info"]["description"] == "共用"
    assert result["paths"]["/b"] == {"get": {"summary": "A"}}
@pytest.mark.parametrize("action, message", [
    ({"target": "$.info", "update": "x"}, "非物件"),
    ({"target": "$.info.title", "update": {"a": 1}}, "純量"),
    ({"target": "$", "remove": True}, "整份文件"),
    ({"target": "$.paths['/pets']", "copy": "$.paths.*"}, "剛好選到一個"),
])
def test_invalid_actions_are_rejected(action, message):
    with pytest.raises(SafeClientError, match=message):
        apply_overlay(SPEC, overlay(action))
def test_unsupported_overlay_version_is_rejected():
    with pytest.raises(SafeClientError, match="Overlay 2.0"):
        apply_overlay(SPEC, {"overlay": "2.0", "info": {}, "actions": [{"target": "$"}]})
@pytest.mark.anyio
async def test_parse_applies_overlays_before_importing():
    hide = overlay({"target": "$.paths.*[?@['x-internal'] == true]", "remove": True})
    result = await OpenApiParser.parse(json.dumps(SPEC), None, [json.dumps(hide)])
    assert [e["name"] for e in result["endpoints"]] == ["listpets"]
@pytest.mark.anyio
async def test_overlay_with_extends_fetches_its_target(monkeypatch):
    fetched = []
    async def fake_fetch(url, purpose):
        fetched.append(url)
        return json.dumps(SPEC)
    monkeypatch.setattr(openapi_documents, "fetch_document_text", fake_fetch)
    document = overlay({"target": "$.paths['/internal/metrics']", "remove": True}, extends="https://specs.example.com/pets.json")
    result = await OpenApiParser.parse(json.dumps(document), None, [])
    assert fetched == ["https://specs.example.com/pets.json"]
    assert sorted(e["name"] for e in result["endpoints"]) == ["deletepet", "listpets"]
@pytest.mark.anyio
async def test_overlay_field_must_hold_an_overlay():
    with pytest.raises(SafeClientError, match="不是 Overlay"):
        await OpenApiParser.parse(json.dumps(SPEC), None, [json.dumps(SPEC)])