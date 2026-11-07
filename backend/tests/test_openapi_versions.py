import json
import pytest
from app.core.error_response import SafeClientError
from app.services import openapi_documents
from app.services.openapi_parser import OpenApiParser
async def parse(spec, base=None):
    return await OpenApiParser.parse(json.dumps(spec) if isinstance(spec, dict) else spec, base, [])
def by_name(result):
    return {e["name"]: e for e in result["endpoints"]}
@pytest.mark.anyio
@pytest.mark.parametrize("field, version, label", [
    ("swagger", "2.0", "swagger_2.0"),
    ("openapi", "3.0.4", "openapi_3.0"),
    ("openapi", "3.1.2", "openapi_3.1"),
    ("openapi", "3.2.0", "openapi_3.2"),
    ("openapi", "3.2.1", "openapi_3.2"),
])
async def test_every_supported_version_is_detected(field, version, label):
    result = await parse({field: version, "info": {"title": "t", "version": "1"}, "paths": {}})
    assert (result["version"], result["spec_version"]) == (label, version)
@pytest.mark.anyio
@pytest.mark.parametrize("spec, message", [
    ({"swaggerVersion": "1.2", "apis": []}, "Swagger 1.2"),
    ({"swagger": "3.0", "paths": {}}, "Swagger 3.0"),
    ({"openapi": "4.0.0", "paths": {}}, "OpenAPI 4.0.0"),
    ({"openapi": "3.3.0", "paths": {}}, "OpenAPI 3.3.0"),
    ({"paths": {"/a": {"get": {}}}}, "無法辨識規格版本"),
])
async def test_unknown_versions_are_rejected(spec, message):
    with pytest.raises(SafeClientError, match=message):
        await parse(spec)
SWAGGER = {
    "swagger": "2.0",
    "info": {"title": "t", "version": "1"},
    "basePath": "/v1",
    "securityDefinitions": {
        "pw": {"type": "oauth2", "flow": "password", "tokenUrl": "https://auth.example.com/token", "scopes": {}},
        "key": {"type": "apiKey", "in": "header", "name": "X-Key"},
    },
    "security": [{"pw": []}, {"key": []}],
    "paths": {
        "/pets": {
            "get": {"operationId": "listPets", "parameters": [
                {"name": "tags", "in": "query", "type": "array", "items": {"type": "string"}},
                {"name": "ids", "in": "query", "type": "array", "items": {"type": "integer"}, "collectionFormat": "multi"},
                {"name": "sizes", "in": "query", "type": "array", "items": {"type": "string"}, "collectionFormat": "pipes"},
            ]},
            "post": {"operationId": "addPet", "parameters": [
                {"name": "body", "in": "body", "required": True, "schema": {"$ref": "#/definitions/NewPet"}},
            ]},
        },
    },
    "definitions": {
        "Pet": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}},
        "NewPet": {"allOf": [{"$ref": "#/definitions/Pet"}, {"properties": {"ownerId": {"type": "integer"}}}]},
    },
}
@pytest.mark.anyio
async def test_swagger_collection_formats_allof_and_host_from_spec_url(monkeypatch):
    async def fake_fetch(url, purpose):
        return json.dumps(SWAGGER)
    monkeypatch.setattr(openapi_documents, "fetch_document_text", fake_fetch)
    result = await parse("https://docs.example.com/specs/pets.json")
    endpoints = by_name(result)
    assert result["base_url"] == "https://docs.example.com/v1"
    styles = endpoints["listpets"]["param_styles"]
    assert (styles["tags"]["style"], styles["tags"]["explode"]) == ("form", False)
    assert (styles["ids"]["style"], styles["ids"]["explode"]) == ("form", True)
    assert styles["sizes"]["style"] == "pipeDelimited"
    assert endpoints["listpets"]["auth_type"] == "api_key"
    assert endpoints["listpets"]["warnings"] == []
    body = endpoints["addpet"]["parameters_schema"]
    assert set(body["properties"]) == {"name", "ownerId"}
    assert body["required"] == ["name"]
OAS30 = {
    "openapi": "3.0.4",
    "info": {"title": "t", "version": "1"},
    "servers": [{"url": "/api/{ver}", "variables": {"ver": {"default": "v2"}}}],
    "components": {
        "securitySchemes": {"session": {"type": "apiKey", "in": "cookie", "name": "SID"}},
        "schemas": {
            "Cat": {"type": "object", "required": ["meow"], "properties": {"meow": {"type": "boolean"}, "id": {"type": "integer", "readOnly": True}}},
            "Dog": {"type": "object", "properties": {"bark": {"type": "boolean"}}},
        },
    },
    "paths": {
        "/pets/{id}": {
            "servers": [{"url": "https://pets.example.com"}],
            "parameters": [
                {"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}},
                {"name": "X-Trace", "in": "header", "required": True, "schema": {"type": "string"}},
                {"name": "Authorization", "in": "header", "schema": {"type": "string"}},
            ],
            "get": {
                "operationId": "getPet",
                "security": [{"session": []}],
                "parameters": [
                    {"name": "X-Trace", "in": "header", "required": False, "schema": {"type": "string"}},
                    {"name": "filter", "in": "query", "style": "deepObject", "explode": True, "schema": {"type": "object"}},
                    {"name": "lang", "in": "cookie", "schema": {"type": "string"}},
                    {"name": "id", "in": "query", "schema": {"type": "integer"}},
                    {"name": "coords", "in": "query", "content": {"application/json": {"schema": {"type": "object"}}}},
                ],
            },
            "put": {
                "operationId": "replacePet",
                "requestBody": {"required": True, "content": {"application/merge-patch+json": {"schema": {
                    "oneOf": [{"$ref": "#/components/schemas/Cat"}, {"$ref": "#/components/schemas/Dog"}],
                    "discriminator": {"propertyName": "kind"},
                }}}},
            },
            "trace": {"operationId": "tracePet"},
        },
    },
}
@pytest.mark.anyio
async def test_oas30_servers_parameters_bodies_and_methods(monkeypatch):
    async def fake_fetch(url, purpose):
        return json.dumps(OAS30)
    monkeypatch.setattr(openapi_documents, "fetch_document_text", fake_fetch)
    result = await parse("https://docs.example.com/openapi.json")
    endpoints = by_name(result)
    assert result["base_url"] == "https://docs.example.com/api/v2"
    assert set(endpoints) == {"getpet", "replacepet", "tracepet"}
    get = endpoints["getpet"]
    assert get["full_url"] == "https://pets.example.com/pets/{id}"
    assert get["param_styles"]["id"]["in"] == "path"
    assert get["param_styles"]["id_query"] == {"name": "id", "in": "query", "style": "form", "explode": True, "allow_reserved": False}
    assert get["param_styles"]["filter"]["style"] == "deepObject"
    assert get["param_styles"]["lang"]["in"] == "cookie"
    assert get["param_styles"]["coords"]["content_type"] == "application/json"
    assert "Authorization" not in get["parameters_schema"]["properties"]
    assert get["parameters_schema"]["required"] == ["id"]
    assert (get["auth_type"], get["auth_config"]["key_in"]) == ("api_key", "cookie")
    put = endpoints["replacepet"]
    assert put["body_content_type"] == "application/merge-patch+json"
    props = put["parameters_schema"]["properties"]
    assert set(props) == {"id", "X-Trace", "meow", "bark", "kind"}
    assert props["id"]["format"] == "uuid"
    assert props["kind"]["enum"] == ["Cat", "Dog"]
    assert "meow" not in put["parameters_schema"]["required"]
    assert "X-Trace" in put["parameters_schema"]["required"]
OAS31 = {
    "openapi": "3.1.2",
    "info": {"title": "t", "summary": "簡介", "version": "1"},
    "servers": [{"url": "https://api.example.com"}],
    "webhooks": {"newPet": {"post": {}}},
    "components": {
        "pathItems": {"Ping": {"get": {"operationId": "ping"}}},
        "schemas": {"Tag": {
            "$id": "https://api.example.com/schemas/tag",
            "type": "object",
            "properties": {
                "label": {"type": ["string", "null"]},
                "kind": {"const": "topic"},
                "meta": {"$ref": "#/$defs/Meta", "description": "補充資料"},
            },
            "$defs": {"Meta": {"type": "object", "properties": {"source": {"type": "string"}}}},
        }},
    },
    "paths": {
        "/ping": {"$ref": "#/components/pathItems/Ping"},
        "/tags": {"post": {"operationId": "createTag", "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Tag"}}}}}},
        "/files/{name}": {"put": {"operationId": "putFile", "parameters": [{"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}],
                                  "requestBody": {"content": {"application/octet-stream": {"schema": {"type": "string", "contentMediaType": "application/octet-stream"}}}}}},
    },
}
@pytest.mark.anyio
async def test_oas31_path_item_refs_json_schema_2020_and_webhooks():
    result = await parse(OAS31)
    endpoints = by_name(result)
    assert set(endpoints) == {"ping", "createtag", "putfile"}
    assert any("webhooks" in w for w in result["warnings"])
    props = endpoints["createtag"]["parameters_schema"]["properties"]
    assert props["label"]["type"] == "string"
    assert props["kind"]["enum"] == ["topic"]
    assert props["meta"] == {"type": "object", "properties": {"source": {"type": "string"}}, "description": "補充資料"}
    put = endpoints["putfile"]
    assert put["body_content_type"] == "application/octet-stream"
    assert put["param_styles"]["request_body"]["whole"] is True
OAS32 = {
    "openapi": "3.2.0",
    "$self": "https://api.example.com/openapi.json",
    "info": {"title": "t", "version": "1"},
    "servers": [{"url": "/v3", "name": "prod"}],
    "components": {"mediaTypes": {"Search": {"schema": {"type": "object", "properties": {"q": {"type": "string"}}}}}},
    "paths": {
        "/search": {
            "query": {"operationId": "searchQuery", "requestBody": {"required": True, "content": {"application/json": {"$ref": "#/components/mediaTypes/Search"}}}},
            "get": {"operationId": "searchGet", "parameters": [{"name": "params", "in": "querystring", "content": {
                "application/x-www-form-urlencoded": {"schema": {"type": "object", "properties": {"q": {"type": "string"}}}}}}]},
            "additionalOperations": {"PURGE": {"operationId": "purgeCache"}, "POST": {"operationId": "ignored"}},
        },
    },
}
@pytest.mark.anyio
async def test_oas32_query_method_additional_operations_querystring_and_self():
    result = await parse(OAS32)
    endpoints = by_name(result)
    assert result["base_url"] == "https://api.example.com/v3"
    assert {(e["method"], e["name"]) for e in endpoints.values()} == {("QUERY", "searchquery"), ("GET", "searchget"), ("PURGE", "purgecache")}
    assert endpoints["searchquery"]["param_styles"]["q"] == {"name": "q", "in": "body"}
    assert endpoints["searchget"]["param_styles"]["params"] == {
        "name": "params", "in": "querystring", "content_type": "application/x-www-form-urlencoded",
    }
@pytest.mark.anyio
async def test_external_refs_are_fetched_relative_to_the_spec(monkeypatch):
    documents = {
        "https://specs.example.com/api/openapi.json": {
            "openapi": "3.0.3", "info": {"title": "t", "version": "1"},
            "paths": {
                "/pets": {"post": {"operationId": "addPet", "requestBody": {"content": {"application/json": {"schema": {"$ref": "schemas/pet.json#/Pet"}}}}}},
                "/owners": {"$ref": "paths/owners.json"},
            },
        },
        "https://specs.example.com/api/schemas/pet.json": {"Pet": {"type": "object", "properties": {"name": {"type": "string"}}}},
        "https://specs.example.com/api/paths/owners.json": {"get": {"operationId": "listOwners"}},
    }
    fetched = []
    async def fake_fetch(url, purpose):
        fetched.append(url)
        return json.dumps(documents[url])
    monkeypatch.setattr(openapi_documents, "fetch_document_text", fake_fetch)
    result = await parse("https://specs.example.com/api/openapi.json")
    endpoints = by_name(result)
    assert endpoints["addpet"]["parameters_schema"]["properties"] == {"name": {"type": "string"}}
    assert "listowners" in endpoints
    assert sorted(fetched) == sorted(documents)
@pytest.mark.anyio
async def test_relative_refs_in_pasted_specs_are_reported():
    spec = {"openapi": "3.0.3", "info": {"title": "t", "version": "1"}, "servers": [{"url": "https://api.example.com"}],
            "paths": {"/pets": {"post": {"operationId": "addPet", "requestBody": {"content": {"application/json": {"schema": {"$ref": "pet.json"}}}}}}}}
    result = await parse(spec)
    assert any("pet.json" in w for w in result["warnings"])
@pytest.mark.anyio
async def test_security_requirements_prefer_usable_schemes_and_report_the_rest():
    spec = {
        "openapi": "3.1.0", "info": {"title": "t", "version": "1"}, "servers": [{"url": "https://api.example.com"}],
        "components": {"securitySchemes": {
            "oidc": {"type": "openIdConnect", "openIdConnectUrl": "https://auth.example.com/.well-known/openid-configuration"},
            "mtls": {"type": "mutualTLS"},
            "key": {"type": "apiKey", "in": "header", "name": "X-Key"},
            "app": {"type": "apiKey", "in": "header", "name": "X-App"},
        }},
        "paths": {
            "/a": {"get": {"operationId": "a", "security": [{"oidc": []}]}},
            "/b": {"get": {"operationId": "b", "security": [{"mtls": []}]}},
            "/c": {"get": {"operationId": "c", "security": [{"key": [], "app": []}]}},
            "/d": {"get": {"operationId": "d", "security": [{}, {"key": []}]}},
        },
    }
    endpoints = by_name(await parse(spec))
    assert endpoints["a"]["auth_type"] == "bearer" and "OpenID Connect" in endpoints["a"]["warnings"][0]
    assert endpoints["b"]["auth_type"] == "none" and "mutualTLS" in endpoints["b"]["warnings"][0]
    assert endpoints["c"]["auth_type"] == "api_key" and endpoints["c"]["headers"] == {"X-App": ""}
    assert endpoints["d"]["auth_type"] == "api_key"
@pytest.mark.anyio
async def test_duplicate_tool_names_get_distinct_suffixes():
    spec = {"openapi": "3.0.3", "info": {"title": "t", "version": "1"}, "servers": [{"url": "https://api.example.com"}],
            "paths": {"/a": {"get": {"operationId": "get-item"}}, "/b": {"get": {"operationId": "get_item"}}}}
    names = [e["name"] for e in (await parse(spec))["endpoints"]]
    assert names == ["get_item", "get_item_2"]