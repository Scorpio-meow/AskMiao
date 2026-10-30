import pytest
import json
from app.models.database import Base, engine, SessionLocal
from app.models import McpServer
from app.services.mcp_service import McpManager
from app.rag.tools import ResearchToolRegistry
@pytest.mark.anyio
async def test_mcp_stdio_lifecycle():
    Base.metadata.create_all(bind=engine)
    presets = McpManager.get_preset_servers()
    time_preset = next(p for p in presets if p["name"] == "mcp_time")
    tools, init_info, _ = await McpManager.discover_server_tools(time_preset)
    assert len(tools) >= 1
    assert tools[0]["name"] == "get_current_time"
    assert init_info.get("protocolVersion") == "2024-11-05"
    call_res = await McpManager.execute_mcp_tool(
        time_preset,
        "get_current_time",
        {"timezone": "Asia/Taipei"}
    )
    assert call_res["is_success"] is True
    assert len(call_res["content"]) >= 1
    assert "當前時間" in call_res["content"][0]["text"]
    db = SessionLocal()
    db.query(McpServer).filter(McpServer.name == "mcp_time_test").delete()
    db.commit()
    server = McpServer(
        name="mcp_time_test",
        display_name="測試時間伺服器",
        description="提供時間查詢",
        transport_type="stdio",
        command=time_preset["command"],
        args=json.dumps(time_preset["args"], ensure_ascii=False),
        discovered_tools=json.dumps(tools, ensure_ascii=False),
        is_enabled=True,
        requires_approval=False,
        status="connected"
    )
    db.add(server)
    db.commit()
    db.refresh(server)
    registry = ResearchToolRegistry()
    defs = registry.get_tool_definitions()
    tool_names = [t["function"]["name"] for t in defs]
    expected_tool_name = "mcp_mcp_time_test_get_current_time"
    assert expected_tool_name in tool_names
    exec_res = await registry.execute_tool(expected_tool_name, {"timezone": "UTC"})
    assert exec_res["is_success"] is True
    assert "當前時間" in exec_res["content"][0]["text"]
    db.delete(server)
    db.commit()
    db.close()
    print("MCP 完整生命週期與調用測試順利通過！")


def test_long_mcp_function_names_are_valid_and_still_dispatch():
    import re
    from app.core.limits import MAX_TOOL_NAME_CHARS

    Base.metadata.create_all(bind=engine)
    server_name = "company-knowledge-graph-production-cluster"
    tool_name = "search_entities_by_relationship_and_attribute_filters"
    db = SessionLocal()
    db.query(McpServer).filter(McpServer.name == server_name).delete()
    db.commit()
    server = McpServer(
        name=server_name,
        display_name="長名稱伺服器",
        transport_type="stdio",
        command="unused",
        discovered_tools=json.dumps([{"name": tool_name}, {"name": tool_name + "_v2"}]),
        is_enabled=True,
        requires_approval=True,
        status="connected",
    )
    db.add(server)
    db.commit()
    try:
        registry = ResearchToolRegistry()
        names = [t["function"]["name"] for t in registry.get_tool_definitions() if t["function"]["name"].startswith("mcp_company")]
        assert len(names) == 2 and len(set(names)) == 2
        for name in names:
            assert re.fullmatch(rf"[a-zA-Z0-9_-]{{1,{MAX_TOOL_NAME_CHARS}}}", name)
        found_server, found_tool = ResearchToolRegistry._find_mcp_tool(db, names[0])
        assert (found_server.name, found_tool) == (server_name, tool_name)
        assert registry.approval_requirement(names[1])["display_name"] == f"長名稱伺服器 → {tool_name}_v2"
    finally:
        db.delete(server)
        db.commit()
        db.close()
