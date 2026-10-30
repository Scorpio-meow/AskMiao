import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import api_tools
from app.core.jwt_auth import get_current_user_from_token
from app.core.limits import MAX_TOOL_NAME_CHARS
from app.models.database import Base, engine, SessionLocal
from app.models import CustomApiTool
from app.services.openapi_parser import OpenApiParser
from app.rag.tools import ResearchToolRegistry
from app.api.api_tools import execute_http_api_tool, _serialize_tool_model
ADMIN_USER = {"user_id": 1, "username": "admin", "email": "admin@example.com", "role": "admin", "is_admin": True}
@pytest.mark.anyio
async def test_custom_api_tools_lifecycle():
    Base.metadata.create_all(bind=engine)
    oas2_yaml = """
swagger: '2.0'
info:
  title: Test Weather API
  version: 1.0.0
host: httpbin.org
basePath: /
schemes:
  - https
paths:
  /get:
    get:
      summary: Get weather by city
      operationId: getWeatherByCity
      parameters:
        - name: city
          in: query
          required: true
          type: string
"""
    parsed = await OpenApiParser.parse(oas2_yaml)
    assert len(parsed["endpoints"]) == 1
    endpoint = parsed["endpoints"][0]
    db = SessionLocal()
    db.query(CustomApiTool).filter(CustomApiTool.name == endpoint["name"]).delete()
    db.commit()
    import json
    new_tool = CustomApiTool(
        name=endpoint["name"],
        display_name=endpoint["display_name"],
        description=endpoint["description"],
        method=endpoint["method"],
        url=endpoint["full_url"],
        base_url=endpoint["base_url"],
        path=endpoint["path"],
        parameters_schema=json.dumps(endpoint["parameters_schema"]),
        param_locations=json.dumps(endpoint["param_locations"]),
        is_enabled=True,
        requires_approval=False,
        spec_version=endpoint["spec_version"]
    )
    db.add(new_tool)
    db.commit()
    db.refresh(new_tool)
    registry = ResearchToolRegistry()
    defs = registry.get_tool_definitions()
    tool_names = [t["function"]["name"] for t in defs]
    assert endpoint["name"] in tool_names
    tool_dict = _serialize_tool_model(new_tool)
    res = await execute_http_api_tool(tool_dict, {"city": "Taipei"}, "test_tool")
    assert res["status_code"] == 200
    assert res["is_success"] is True
    assert "Taipei" in str(res["data"])
    new_tool.is_enabled = False
    db.commit()
    defs_after = registry.get_tool_definitions()
    tool_names_after = [t["function"]["name"] for t in defs_after]
    assert endpoint["name"] not in tool_names_after
    db.delete(new_tool)
    db.commit()
    db.close()
    print("Custom API Tools 完整生命週期測試通過！")


def admin_client():
    app = FastAPI()
    app.include_router(api_tools.router, prefix="/api/api-tools")
    app.dependency_overrides[get_current_user_from_token] = lambda: ADMIN_USER
    return TestClient(app)


def import_item(name, **fields):
    return {"name": name, "display_name": name, "description": "d", "method": "GET", "path": "/x",
            "full_url": "https://api.example.com/x", **fields}


def test_tool_names_over_the_limit_are_rejected():
    Base.metadata.create_all(bind=engine)
    client = admin_client()
    long_name = "a" * (MAX_TOOL_NAME_CHARS + 1)
    created = client.post("/api/api-tools", json={"name": long_name, "display_name": "d", "description": "d",
                                                  "method": "GET", "url": "https://api.example.com/x"})
    assert created.status_code == 400
    imported = client.post("/api/api-tools/import", json={"tools": [import_item(long_name)]})
    assert imported.status_code == 400
    with SessionLocal() as db:
        assert db.query(CustomApiTool).filter(CustomApiTool.name == long_name).count() == 0


def test_reimport_keeps_stored_credentials_and_enabled_state(existing_users):
    existing_users(ADMIN_USER)
    name = "reimport_keeps_credentials"
    with SessionLocal() as db:
        db.query(CustomApiTool).filter(CustomApiTool.name == name).delete()
        db.commit()
    client = admin_client()
    spec_auth = {"auth_type": "api_key", "auth_config": {"key_name": "X-API-Key", "key_in": "header", "key_value": ""}}
    try:
        assert client.post("/api/api-tools/import", json={"tools": [import_item(name, **spec_auth)]}).status_code == 200
        with SessionLocal() as db:
            tool_id = db.query(CustomApiTool).filter(CustomApiTool.name == name).one().id
        client.put(f"/api/api-tools/{tool_id}", json={
            "headers": {"X-Tenant": "tenant-1"},
            "auth_config": {"key_name": "X-API-Key", "key_in": "header", "key_value": "secret-1"},
            "is_enabled": False,
        })

        def stored():
            with SessionLocal() as db:
                return _serialize_tool_model(db.query(CustomApiTool).filter(CustomApiTool.id == tool_id).one())

        assert client.post("/api/api-tools/import", json={"tools": [import_item(name, **spec_auth)]}).json()["updated"] == 1
        tool = stored()
        assert tool["headers"] == {"X-Tenant": "tenant-1"}
        assert (tool["auth_type"], tool["auth_config"]["key_value"]) == ("api_key", "secret-1")
        assert tool["is_enabled"] is False

        client.post("/api/api-tools/import", json={
            "tools": [import_item(name, **spec_auth)],
            "global_headers": {"Accept": "application/json"},
            "global_auth_type": "api_key",
            "global_auth_config": {"key_value": "secret-2"},
        })
        tool = stored()
        assert tool["headers"] == {"X-Tenant": "tenant-1", "Accept": "application/json"}
        assert tool["auth_config"]["key_value"] == "secret-2"

        client.put(f"/api/api-tools/{tool_id}", json={"auth_type": "bearer", "auth_config": {"token": "bearer-1"}})
        client.post("/api/api-tools/import", json={"tools": [import_item(name, **spec_auth)]})
        tool = stored()
        assert (tool["auth_type"], tool["auth_config"]) == ("bearer", {"token": "bearer-1"})
    finally:
        with SessionLocal() as db:
            db.query(CustomApiTool).filter(CustomApiTool.name == name).delete()
            db.commit()


@pytest.mark.anyio
async def test_stored_tool_name_over_the_limit_is_fitted_for_the_model(existing_users, monkeypatch):
    import re
    from app.services.openapi_parser import fit_tool_name

    existing_users(ADMIN_USER)
    name = "legacy_" + "x" * 63
    with SessionLocal() as db:
        db.query(CustomApiTool).filter(CustomApiTool.name == name).delete()
        db.add(CustomApiTool(name=name, display_name="舊工具", description="d", method="POST", url="https://api.example.com/x",
                             is_enabled=True, requires_approval=True, created_by=ADMIN_USER["user_id"]))
        db.commit()
    calls = []

    async def fake_execute(tool_dict, arguments, tool_name):
        calls.append((tool_dict["name"], arguments))
        return {"ok": True}

    monkeypatch.setattr(api_tools, "execute_http_api_tool", fake_execute)
    try:
        registry = ResearchToolRegistry()
        fitted = fit_tool_name(name)
        names = [t["function"]["name"] for t in registry.get_tool_definitions()]
        assert len(name) == 70 and fitted in names and name not in names
        assert re.fullmatch(rf"[a-zA-Z0-9_-]{{1,{MAX_TOOL_NAME_CHARS}}}", fitted)
        assert registry.approval_requirement(fitted)["display_name"] == "舊工具"
        assert await registry.execute_tool(fitted, {"q": 1}) == {"ok": True}
        assert calls == [(name, {"q": 1})]
    finally:
        with SessionLocal() as db:
            db.query(CustomApiTool).filter(CustomApiTool.name == name).delete()
            db.commit()
