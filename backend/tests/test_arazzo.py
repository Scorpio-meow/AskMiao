import ipaddress
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.api.api_tools import execute_api_tool
from app.core.error_response import SafeClientError
from app.services import arazzo, oauth_client, openapi_documents
from app.services.openapi_parser import OpenApiParser

PUBLIC_IP = ipaddress.ip_address("93.184.216.34")
PETSTORE_URL = "https://specs.example.com/petstore.json"
PETSTORE = {
    "openapi": "3.1.0",
    "info": {"title": "Pets", "version": "1"},
    "servers": [{"url": "https://api.example.com"}],
    "components": {"securitySchemes": {"key": {"type": "apiKey", "in": "header", "name": "X-Key"}}},
    "security": [{"key": []}],
    "paths": {
        "/pets": {"get": {"operationId": "findPets", "parameters": [{"name": "status", "in": "query", "schema": {"type": "string"}}]}},
        "/pets/{petId}/adopt": {"post": {"operationId": "adoptPet", "parameters": [{"name": "petId", "in": "path", "required": True, "schema": {"type": "integer"}}],
                                         "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"owner": {"type": "string"}}}}}}}},
        "/health": {"get": {"operationId": "health"}},
    },
}
ARAZZO = {
    "arazzo": "1.1.0",
    "info": {"title": "Adoption", "version": "1"},
    "sourceDescriptions": [{"name": "petstore", "url": "petstore.json", "type": "openapi"}],
    "components": {
        "parameters": {"available": {"name": "status", "in": "query", "value": "available"}},
        "failureActions": {"retryOnce": {"name": "retryOnce", "type": "retry", "retryAfter": 0, "retryLimit": 1,
                                         "criteria": [{"condition": "$statusCode == 503"}]}},
    },
    "workflows": [
        {
            "workflowId": "adoptFirstPet",
            "summary": "領養第一隻可領養的寵物",
            "inputs": {"type": "object", "required": ["owner"], "properties": {"owner": {"type": "string"}}},
            "dependsOn": ["checkHealth"],
            "steps": [
                {
                    "stepId": "find",
                    "operationId": "$sourceDescriptions.petstore.findPets",
                    "parameters": [{"reference": "$components.parameters.available"}],
                    "successCriteria": [
                        {"condition": "$statusCode == 200"},
                        {"context": "$response.body", "condition": "$.pets[?@.id]", "type": "jsonpath"},
                    ],
                    "outputs": {"petId": "$response.body#/pets/0/id", "name": {"context": "$response.body", "selector": "$.pets[0].name", "type": "jsonpath"}},
                    "onFailure": [{"reference": "$components.failureActions.retryOnce"}],
                },
                {
                    "stepId": "adopt",
                    "operationPath": "{$sourceDescriptions.petstore.url}#/paths/~1pets~1{petId}~1adopt/post",
                    "parameters": [{"name": "petId", "in": "path", "value": "$steps.find.outputs.petId"}],
                    "requestBody": {"contentType": "application/json", "payload": {"owner": "$inputs.owner", "note": "領養 {$steps.find.outputs.name}"},
                                    "replacements": [{"target": "/source", "value": "askmiao"}]},
                    "successCriteria": [{"condition": "$statusCode == 201 && $response.body#/status == 'ADOPTED'"}],
                    "outputs": {"adoption": "$response.body#/id"},
                },
            ],
            "outputs": {"adoptionId": "$steps.adopt.outputs.adoption", "health": "$workflows.checkHealth.outputs.status"},
        },
        {
            "workflowId": "checkHealth",
            "steps": [{"stepId": "ping", "operationId": "health", "successCriteria": [{"context": "$response.body#/status", "condition": "^ok$", "type": "regex"}],
                       "outputs": {"status": "$response.body#/status"}}],
            "outputs": {"status": "$steps.ping.outputs.status"},
        },
        {
            "workflowId": "loopForever",
            "steps": [{"stepId": "again", "operationId": "health", "onSuccess": [{"name": "loop", "type": "goto", "stepId": "again"}]}],
        },
    ],
}


@pytest.fixture
def sources(monkeypatch):
    documents = {PETSTORE_URL: PETSTORE, "https://specs.example.com/adoption.arazzo.json": ARAZZO}

    async def fake_fetch(url, purpose):
        return json.dumps(documents[url])

    monkeypatch.setattr(openapi_documents, "fetch_document_text", fake_fetch)


@pytest.fixture
def upstream(monkeypatch):
    state = {"sent": [], "responses": {}}

    async def fake_send(self, request):
        await request.aread()
        state["sent"].append(request)
        key = f"{request.method} {request.url.path}"
        queue = state["responses"][key]
        status, body = queue.pop(0) if len(queue) > 1 else queue[0]
        return httpx.Response(status, json=body, request=request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_send)
    oauth_client._token_cache.clear()
    with patch("app.core.ssrf_protection.resolve_hostname", new_callable=AsyncMock) as mock_dns:
        mock_dns.return_value = [PUBLIC_IP]
        yield state


async def imported(name):
    result = await OpenApiParser.parse("https://specs.example.com/adoption.arazzo.json", None, [])
    endpoint = next(e for e in result["endpoints"] if e["name"] == name)
    return result, {
        "name": endpoint["name"], "method": endpoint["method"], "url": endpoint["full_url"],
        "parameters_schema": endpoint["parameters_schema"], "workflow_definition": endpoint["workflow_definition"],
        "auth_type": endpoint["auth_type"], "auth_config": {"key_name": "X-Key", "key_in": "header", "key_value": "k-secret"},
        "headers": {}, "timeout": 5,
    }


@pytest.mark.anyio
async def test_arazzo_document_becomes_one_tool_per_workflow(sources):
    result, tool = await imported("workflow_adoptfirstpet")
    assert (result["kind"], result["version"]) == ("arazzo", "arazzo_1.1")
    names = {e["name"]: e for e in result["endpoints"]}
    assert set(names) == {"workflow_adoptfirstpet", "workflow_checkhealth", "workflow_loopforever"}
    adopt = names["workflow_adoptfirstpet"]
    assert adopt["parameters_schema"]["required"] == ["owner"]
    assert adopt["requires_approval"] is True
    assert names["workflow_checkhealth"]["requires_approval"] is False
    assert adopt["workflow_definition"]["step_targets"] == ["GET api.example.com", "POST api.example.com"]
    assert adopt["auth_type"] == "api_key"


@pytest.mark.anyio
async def test_workflow_runs_steps_passes_outputs_and_retries(sources, upstream):
    upstream["responses"] = {
        "GET /health": [(200, {"status": "ok"})],
        "GET /pets": [(503, {}), (200, {"pets": [{"id": 42, "name": "Mimi"}]})],
        "POST /pets/42/adopt": [(201, {"id": "A-1", "status": "adopted"})],
    }
    _, tool = await imported("workflow_adoptfirstpet")
    result = await execute_api_tool(tool, {"owner": "小明"}, tool["name"])
    assert result["is_success"] is True, json.dumps(result, ensure_ascii=False)
    assert result["outputs"] == {"adoptionId": "A-1", "health": "ok"}
    assert [(s["step"], s["success"]) for s in result["steps"]] == [("ping", True), ("find", False), ("find", True), ("adopt", True)]
    find, adopt = upstream["sent"][2], upstream["sent"][3]
    assert find.url.query.decode() == "status=available"
    assert find.headers["x-key"] == "k-secret"
    assert json.loads(adopt.content) == {"owner": "小明", "note": "領養 Mimi", "source": "askmiao"}
    assert "k-secret" not in json.dumps(result, ensure_ascii=False)


@pytest.mark.anyio
async def test_failed_criteria_stop_the_workflow(sources, upstream):
    upstream["responses"] = {
        "GET /health": [(200, {"status": "ok"})],
        "GET /pets": [(200, {"pets": []})],
    }
    _, tool = await imported("workflow_adoptfirstpet")
    result = await execute_api_tool(tool, {"owner": "小明"}, tool["name"])
    assert result["is_success"] is False
    assert "find" in result["error"]
    assert [r.url.path for r in upstream["sent"]] == ["/health", "/pets"]


@pytest.mark.anyio
async def test_loops_are_stopped_by_the_step_budget(sources, upstream):
    upstream["responses"] = {"GET /health": [(200, {"status": "ok"})]}
    _, tool = await imported("workflow_loopforever")
    result = await execute_api_tool(tool, {}, tool["name"])
    assert result["is_success"] is False and "上限" in result["error"]


@pytest.mark.anyio
async def test_workflow_inputs_are_checked(sources, upstream):
    _, tool = await imported("workflow_adoptfirstpet")
    result = await execute_api_tool(tool, {"owner": "小明", "admin": True}, tool["name"])
    assert result["status_code"] == 400 and "admin" in result["error"]
    assert upstream["sent"] == []


def test_simple_conditions_follow_the_arazzo_rules():
    run = arazzo._Run({"workflow_definition": {"workflows": {}}}, "t")
    scope = {"exchange": {"status_code": 200, "response": {"body": {"items": [{"name": "Mimi"}], "count": 3}, "header": {}}}}
    assert run.simple("$statusCode == 200 && !($response.body#/count < 2)", scope)
    assert run.simple("$response.body#/items[0].name == 'mimi'", scope)
    assert run.simple("$response.body#/missing == null", scope)
    assert not run.simple("$statusCode != 200 || $response.body#/count > 5", scope)


@pytest.mark.anyio
async def test_unsupported_arazzo_versions_and_sources_are_reported(sources):
    with pytest.raises(SafeClientError, match="Arazzo 2.0"):
        await OpenApiParser.parse(json.dumps({"arazzo": "2.0.0", "info": {}, "workflows": []}), None, [])
    doc = {"arazzo": "1.0.1", "info": {"title": "t", "version": "1"},
           "sourceDescriptions": [{"name": "events", "url": "https://specs.example.com/events.yaml", "type": "asyncapi"}],
           "workflows": [{"workflowId": "w", "steps": [{"stepId": "s", "operationId": "send"}]}]}
    result = await OpenApiParser.parse(json.dumps(doc), None, [])
    assert any("asyncapi" in w for w in result["warnings"])
    assert any("找不到 operationId" in w for w in result["endpoints"][0]["warnings"])
