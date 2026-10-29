import io
import json
import zipfile
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import skills as skills_api
from app.core.config import settings
from app.core.jwt_auth import get_current_user_from_token
from app.core.user_context import get_current_user_id
from app.models import AgentSkill, User
from app.models.database import Base, SessionLocal, engine
from app.rag.agent import ResearchAgent
from app.rag.tools import ResearchToolRegistry
from app.services import agent_skills
from test_agent_guardrails import ScriptedLLM, answer, collect, research, tool_call

ADMIN_USER = {"user_id": 1, "username": "admin", "email": "admin@example.com", "role": "admin", "is_admin": True}
USERNAMES = ("skill_member_a", "skill_member_b")

SKILL_MD = """---
name: script-skill
description: Runs helper scripts. Use when testing scripts.
allowed-tools: run_skill_script Read
---
Run scripts/echo.py.
"""

ECHO_PY = """import os, sys
data = sys.stdin.read()
open("written.txt", "w").write("x")
print("args=" + ",".join(sys.argv[1:]))
print("stdin=" + data)
print("secret=" + os.environ.get("DATABASE_URL", "absent"))
print("x" * int(os.environ.get("NO_SUCH", "0")))
"""


def make_zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path, content in entries.items():
            archive.writestr(path, content)
    return buffer.getvalue()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@db/x")
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.query(AgentSkill).delete()
        db.query(User).filter(User.username.in_(USERNAMES)).delete(synchronize_session=False)
        users = []
        for name in USERNAMES:
            user = User(username=name, email=f"{name}@example.com", hashed_password="x", is_active=True, is_admin=False,
                        role="user", created_at=datetime.utcnow(), tokens_valid_after=datetime.utcnow())
            db.add(user)
            users.append(user)
        db.commit()
        ids = [u.id for u in users]
    app = FastAPI()
    app.include_router(skills_api.router, prefix="/api/skills")
    app.dependency_overrides[get_current_user_from_token] = lambda: ADMIN_USER
    app.dependency_overrides[get_current_user_id] = lambda: ADMIN_USER["user_id"]
    client = TestClient(app)
    response = client.post("/api/skills/upload", files={"file": ("s.zip", make_zip({
        "SKILL.md": SKILL_MD,
        "scripts/echo.py": ECHO_PY,
        "scripts/sleep.py": "import time\ntime.sleep(30)\n",
        "scripts/loud.py": "print('y' * 300000)\n",
        "scripts/tool.exe": "MZ",
    }), "application/zip")})
    assert response.status_code == 200, response.text
    yield client, response.json()["skill"], ids
    with SessionLocal() as db:
        db.query(AgentSkill).delete()
        db.query(User).filter(User.username.in_(USERNAMES)).delete(synchronize_session=False)
        db.commit()


def tool(definitions, name):
    return next((t for t in definitions if t["function"]["name"] == name), None)


@pytest.mark.anyio
async def test_scripts_require_opt_in(env):
    _, _, _ = env
    registry = ResearchToolRegistry()
    assert tool(registry.get_tool_definitions(), "run_skill_script") is None
    result = await registry.execute_tool("run_skill_script", {"skill": "script-skill", "path": "scripts/echo.py"})
    assert "不允許執行腳本" in result["error"]


@pytest.mark.anyio
async def test_script_runs_isolated_with_args_and_stdin(env):
    client, skill, _ = env
    assert client.patch(f"/api/skills/{skill['id']}/settings", json={"allow_scripts": True}).json()["skill"]["allow_scripts"] is True
    registry = ResearchToolRegistry()
    definition = tool(registry.get_tool_definitions(), "run_skill_script")
    assert definition["function"]["parameters"]["properties"]["skill"]["enum"] == ["script-skill"]

    result = await registry.execute_tool(
        "run_skill_script", {"skill": "script-skill", "path": "scripts/echo.py", "args": ["a", "b"], "stdin": "hello"}
    )
    assert result["exit_code"] == 0, result
    assert "args=a,b" in result["stdout"] and "stdin=hello" in result["stdout"]
    assert "secret=absent" in result["stdout"]
    assert not (agent_skills.skill_directory("script-skill") / "written.txt").exists()

    loud = await registry.execute_tool("run_skill_script", {"skill": "script-skill", "path": "scripts/loud.py"})
    assert loud["output_truncated"] is True and len(loud["stdout"]) <= 20_000

    for bad in ({"path": "scripts/tool.exe"}, {"path": "../x.py"}, {"path": "scripts/echo.py", "args": "not-a-list"}):
        assert "error" in await registry.execute_tool("run_skill_script", {"skill": "script-skill", **bad})


@pytest.mark.anyio
async def test_script_timeout_kills_process(env, monkeypatch):
    client, skill, _ = env
    client.patch(f"/api/skills/{skill['id']}/settings", json={"allow_scripts": True})
    monkeypatch.setattr(agent_skills, "MAX_SKILL_SCRIPT_SECONDS", 1)
    result = await ResearchToolRegistry().execute_tool("run_skill_script", {"skill": "script-skill", "path": "scripts/sleep.py"})
    assert result["timed_out"] is True
    assert result["duration_seconds"] < 15


def test_script_approval_names_the_command(env):
    requirement = ResearchToolRegistry().approval_requirement("run_skill_script", {"skill": "script-skill", "path": "scripts/echo.py"})
    assert requirement["kind"] == "skill_script"
    assert requirement["display_name"] == "script-skill → scripts/echo.py"
    assert requirement["target"].startswith("本機指令 python")


@pytest.mark.anyio
async def test_allowed_tools_preapprove_only_after_activation(env, monkeypatch):
    client, skill, _ = env
    client.patch(f"/api/skills/{skill['id']}/settings", json={"allow_scripts": True})
    registry = ResearchToolRegistry()
    agent = ResearchAgent(tool_registry=registry)
    llm = ScriptedLLM([
        tool_call("run_skill_script", {"skill": "script-skill", "path": "scripts/echo.py"}, "c1"),
        tool_call("activate_skill", {"name": "script-skill"}, "c2"),
        tool_call("run_skill_script", {"skill": "script-skill", "path": "scripts/echo.py"}, "c3"),
        answer("完成"),
    ])
    llm.install(monkeypatch)
    events = await collect(research(agent, "跑腳本", approval_user_id=None))
    steps = [e["data"] for e in events if e["event"] == "step_end"]
    assert "核准" in steps[0]["output_preview"]
    assert steps[1]["status"] == "success"
    assert '"exit_code": 0' in steps[2]["output_preview"]
    assert not any(e["event"] == "approval_required" for e in events)


@pytest.mark.anyio
async def test_skill_restricted_to_users(env):
    client, skill, (member_a, member_b) = env
    assert client.patch(f"/api/skills/{skill['id']}/settings", json={"allowed_user_ids": [999999]}).status_code == 400
    updated = client.patch(f"/api/skills/{skill['id']}/settings", json={"allowed_user_ids": [member_a]}).json()["skill"]
    assert updated["allowed_user_ids"] == [member_a]

    registry = ResearchToolRegistry()
    assert tool(registry.get_tool_definitions(member_a), "activate_skill") is not None
    assert tool(registry.get_tool_definitions(member_b), "activate_skill") is None
    assert tool(registry.get_tool_definitions(), "activate_skill") is None
    assert "error" in await registry.execute_tool("activate_skill", {"name": "script-skill"}, user_id=member_b)
    assert "content" in await registry.execute_tool("activate_skill", {"name": "script-skill"}, user_id=member_a)

    cleared = client.patch(f"/api/skills/{skill['id']}/settings", json={"allowed_user_ids": []}).json()["skill"]
    assert cleared["allowed_user_ids"] is None
    assert tool(registry.get_tool_definitions(member_b), "activate_skill") is not None


def test_empty_allow_list_means_nobody():
    assert agent_skills.skill_visible_to(None, 5) is True
    assert agent_skills.skill_visible_to(json.dumps([5]), 5) is True
    assert agent_skills.skill_visible_to(json.dumps([]), 5) is False
    assert agent_skills.skill_visible_to(json.dumps([5]), None) is False
