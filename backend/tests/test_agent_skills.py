import io
import stat
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import skills as skills_api
from app.core.config import settings
from app.core.jwt_auth import get_current_user_from_token
from app.core.user_context import get_current_user_id
from app.models import AgentSkill
from app.models.database import SessionLocal
from app.rag.agent import ResearchAgent
from app.rag.research_session import ResearchSession
from app.rag.tools import ResearchToolRegistry
from app.services import agent_skills
from app.services.agent_skills import SkillError, parse_skill_md, read_skill_folder, read_skill_upload
from test_agent_guardrails import research

NORMAL_USER = {"user_id": 2, "username": "member", "email": "member@example.com", "role": "user", "is_admin": False}
ADMIN_USER = {"user_id": 1, "username": "admin", "email": "admin@example.com", "role": "admin", "is_admin": True}

PDF_SKILL = """---
name: pdf-processing
description: Extract PDF text and fill forms. Use when handling PDFs.
license: Apache-2.0
metadata:
  author: example-org
  version: 1.0
---
# PDF Processing

See [the reference](references/REFERENCE.md).
"""


def make_zip(entries, symlinks=()):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path, content in entries.items():
            archive.writestr(path, content)
        for path in symlinks:
            info = zipfile.ZipInfo(path)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "/etc/passwd")
    return buffer.getvalue()


@pytest.fixture
def skills_dir(tmp_path, monkeypatch, existing_users):
    monkeypatch.setattr(settings, "SKILLS_DIR", str(tmp_path / "skills"))
    existing_users(ADMIN_USER, NORMAL_USER)
    db = SessionLocal()
    db.query(AgentSkill).delete()
    db.commit()
    db.close()
    yield tmp_path / "skills"
    db = SessionLocal()
    db.query(AgentSkill).delete()
    db.commit()
    db.close()


def client_for(user):
    app = FastAPI()
    app.include_router(skills_api.router, prefix="/api/skills")
    app.dependency_overrides[get_current_user_from_token] = lambda: user
    app.dependency_overrides[get_current_user_id] = lambda: user["user_id"]
    return TestClient(app)


def upload(client, filename, data, replace=False):
    return client.post(
        "/api/skills/upload",
        params={"replace": str(replace).lower()},
        files={"file": (filename, data, "application/octet-stream")},
    )


def upload_folder(client, entries, replace=False):
    return client.post(
        "/api/skills/upload-folder",
        params={"replace": str(replace).lower()},
        files=[("files", (path, data, "application/octet-stream")) for path, data in entries],
    )


PDF_FOLDER = [
    ("pdf-processing/SKILL.md", PDF_SKILL.encode()),
    ("pdf-processing/references/REFERENCE.md", "參考內容".encode()),
]


def test_parse_valid_skill_keeps_optional_fields():
    skill = parse_skill_md(PDF_SKILL)
    assert skill.name == "pdf-processing"
    assert skill.license == "Apache-2.0"
    assert skill.metadata == {"author": "example-org", "version": "1.0"}
    assert skill.body.startswith("# PDF Processing")
    assert skill.warnings == []


def test_parse_accepts_unquoted_colon_in_description():
    skill = parse_skill_md("---\nname: demo\ndescription: Use this skill when: the user asks about PDFs\n---\nbody")
    assert skill.description == "Use this skill when: the user asks about PDFs"


@pytest.mark.parametrize("text, message", [
    ("no frontmatter", "frontmatter"),
    ("---\nname: demo\n---\nbody", "description"),
    ("---\nname: PDF-Tool\ndescription: x\n---\n", "不合規"),
    ("---\nname: pdf--tool\ndescription: x\n---\n", "不合規"),
    ("---\nname: -pdf\ndescription: x\n---\n", "不合規"),
    ("---\nname: demo\ndescription: x\n", "結尾"),
])
def test_parse_rejects_invalid_skill(text, message):
    with pytest.raises(SkillError, match=message):
        parse_skill_md(text)


def test_parse_warns_but_loads_on_cosmetic_issues():
    skill = parse_skill_md("---\nname: demo\ndescription: d\nfoo: bar\n---\nbody", directory_name="other")
    assert any("other" in w for w in skill.warnings)
    assert any("foo" in w for w in skill.warnings)


def test_zip_with_top_directory_is_unwrapped():
    data = make_zip({
        "pdf-processing/SKILL.md": PDF_SKILL,
        "pdf-processing/references/REFERENCE.md": "ref",
        "__MACOSX/pdf-processing/._SKILL.md": "junk",
    })
    skill, files = read_skill_upload("pdf.zip", data)
    assert skill.name == "pdf-processing"
    assert set(files) == {("SKILL.md",), ("references", "REFERENCE.md")}


@pytest.mark.parametrize("entries, symlinks, message", [
    ({"SKILL.md": PDF_SKILL, "../evil.txt": "x"}, (), "不安全"),
    ({"SKILL.md": PDF_SKILL, "/abs.txt": "x"}, (), "不安全"),
    ({"SKILL.md": PDF_SKILL, "a/D:/evil.txt": "x"}, (), "不安全"),
    ({"SKILL.md": PDF_SKILL}, ("link",), "符號連結"),
    ({"a/SKILL.md": PDF_SKILL, "b/x.md": "x"}, (), "找不到 SKILL.md"),
])
def test_zip_rejects_unsafe_archives(entries, symlinks, message):
    with pytest.raises(SkillError, match=message):
        read_skill_upload("skill.zip", make_zip(entries, symlinks))


def test_zip_rejects_too_many_files(monkeypatch):
    monkeypatch.setattr(agent_skills, "MAX_SKILL_FILES", 2)
    with pytest.raises(SkillError, match="檔案數"):
        read_skill_upload("skill.zip", make_zip({"SKILL.md": PDF_SKILL, "a": "1", "b": "2"}))


def test_zip_rejects_oversized_content(monkeypatch):
    monkeypatch.setattr(agent_skills, "MAX_SKILL_UNCOMPRESSED_BYTES", 1024)
    with pytest.raises(SkillError, match="MiB"):
        read_skill_upload("skill.zip", make_zip({"SKILL.md": PDF_SKILL, "big.txt": "x" * 4096}))


def test_upload_rejects_unknown_extension():
    with pytest.raises(SkillError, match="zip"):
        read_skill_upload("skill.exe", b"MZ")


def skill_md(name, description="Use when testing."):
    return f"---\nname: {name}\ndescription: {description}\n---\nbody".encode()


def test_folder_with_top_directory_is_unwrapped():
    [found] = read_skill_folder(PDF_FOLDER + [
        ("pdf-processing/.git/config", b"junk"),
        ("pdf-processing/.DS_Store", b"junk"),
    ])
    assert found.path == "pdf-processing"
    assert found.error is None
    assert found.skill.name == "pdf-processing"
    assert found.skill.warnings == []
    assert found.files == {("SKILL.md",): PDF_SKILL.encode(), ("references", "REFERENCE.md"): "參考內容".encode()}


def test_folder_named_differently_warns():
    [found] = read_skill_folder([("my-pdf\\SKILL.md", PDF_SKILL.encode())])
    assert set(found.files) == {("SKILL.md",)}
    assert any("my-pdf" in w for w in found.skill.warnings)


def test_folder_of_skills_finds_each_outermost_skill():
    found = read_skill_folder([
        ("skills/README.md", b"collection"),
        ("skills/beta/SKILL.md", skill_md("beta")),
        ("skills/alpha/SKILL.md", skill_md("alpha")),
        ("skills/alpha/examples/nested/SKILL.md", skill_md("nested")),
        ("skills/group/gamma/SKILL.md", skill_md("gamma")),
        ("skills/broken/SKILL.md", b"no frontmatter"),
    ])
    assert [item.path for item in found] == ["skills/alpha", "skills/beta", "skills/broken", "skills/group/gamma"]
    alpha = found[0]
    assert set(alpha.files) == {("SKILL.md",), ("examples", "nested", "SKILL.md")}
    assert found[2].skill is None and "frontmatter" in found[2].error
    assert found[3].skill.name == "gamma"


def test_folder_limits_files_per_skill(monkeypatch):
    monkeypatch.setattr(agent_skills, "MAX_SKILL_FILES", 2)
    found = read_skill_folder([
        ("skills/small/SKILL.md", skill_md("small")),
        ("skills/large/SKILL.md", skill_md("large")),
        ("skills/large/a.md", b"a"),
        ("skills/large/b.md", b"b"),
    ])
    assert [(item.path, item.error is None) for item in found] == [("skills/large", False), ("skills/small", True)]
    assert "檔案數" in found[0].error


@pytest.mark.parametrize("entries, message", [
    ([("skill/SKILL.md", PDF_SKILL.encode()), ("skill/../evil.txt", b"x")], "不安全"),
    ([("C:/skill/SKILL.md", PDF_SKILL.encode())], "不安全"),
    ([("/skill/SKILL.md", PDF_SKILL.encode())], "不安全"),
    ([("skill/SKILL.md", PDF_SKILL.encode()), ("skill/D:/evil.py", b"x")], "不安全"),
    ([("skill/SKILL.md", PDF_SKILL.encode()), ("skill/notes.md:hidden", b"x")], "不安全"),
    ([("skill/README.md", b"x")], "找不到 SKILL.md"),
    ([("skill/.git/SKILL.md", PDF_SKILL.encode())], "找不到 SKILL.md"),
])
def test_folder_rejects_invalid_selection(entries, message):
    with pytest.raises(SkillError, match=message):
        read_skill_folder(entries)


def test_install_and_read_resources(skills_dir):
    skill, files = read_skill_upload("pdf.zip", make_zip({
        "SKILL.md": PDF_SKILL,
        "references/REFERENCE.md": "參考內容",
        "assets/logo.bin": b"\xff\xfe\x00\x81",
    }))
    agent_skills.install_skill(skill, files, replace=False)
    resources, truncated = agent_skills.list_skill_resources("pdf-processing")
    assert resources == ["assets/logo.bin", "references/REFERENCE.md"]
    assert truncated is False

    result = agent_skills.read_skill_resource("pdf-processing", "references/REFERENCE.md")
    assert "參考內容" in result["content"]
    assert result["content"].startswith('<skill_resource skill="pdf-processing"')
    assert "error" in agent_skills.read_skill_resource("pdf-processing", "assets/logo.bin")
    for bad in ("../pdf-processing/SKILL.md", "/etc/passwd", "C:/Windows/win.ini", "missing.md", ""):
        assert "error" in agent_skills.read_skill_resource("pdf-processing", bad)

    with pytest.raises(SkillError, match="同名"):
        agent_skills.install_skill(skill, files, replace=False)
    agent_skills.install_skill(skill, {("SKILL.md",): PDF_SKILL.encode()}, replace=True)
    assert agent_skills.list_skill_resources("pdf-processing") == ([], False)
    assert [p.name for p in skills_dir.iterdir()] == ["pdf-processing"]


def test_install_rejects_conflicting_entries(skills_dir):
    skill, files = read_skill_upload("pdf.zip", make_zip({"SKILL.md": PDF_SKILL, "a": "file", "a/b.md": "nested"}))
    with pytest.raises(SkillError, match="無法寫入"):
        agent_skills.install_skill(skill, files, replace=False)
    assert [p.name for p in skills_dir.iterdir()] == []


def test_activation_content_lists_resources_without_reading_them(skills_dir):
    skill, files = read_skill_upload("pdf.zip", make_zip({"SKILL.md": PDF_SKILL, "scripts/run.py": "print(1)"}))
    agent_skills.install_skill(skill, files, replace=False)
    content = agent_skills.activate_skill("pdf-processing", False)["content"]
    assert content.startswith('<skill_content name="pdf-processing">')
    assert "<file>scripts/run.py</file>" in content
    assert "print(1)" not in content
    assert "name: pdf-processing" not in content
    assert "本系統不會執行技能內的腳本" in content
    scripted = agent_skills.activate_skill("pdf-processing", True)["content"]
    assert "run_skill_script" in scripted
    assert "不會執行" not in scripted


def test_non_admin_cannot_manage_skills(skills_dir):
    client = client_for(NORMAL_USER)
    assert client.get("/api/skills").status_code == 403
    assert upload(client, "SKILL.md", PDF_SKILL.encode()).status_code == 403
    assert client.patch("/api/skills/1/toggle").status_code == 403
    assert client.delete("/api/skills/1").status_code == 403
    assert client.get("/api/skills/enabled").status_code == 200
    assert not skills_dir.exists()


def test_admin_skill_lifecycle(skills_dir):
    admin = client_for(ADMIN_USER)
    member = client_for(NORMAL_USER)
    response = upload(admin, "pdf.zip", make_zip({"SKILL.md": PDF_SKILL, "references/REFERENCE.md": "ref"}))
    assert response.status_code == 200, response.text
    skill = response.json()["skill"]
    assert skill["name"] == "pdf-processing" and skill["is_enabled"] and skill["files_present"]

    assert upload(admin, "SKILL.md", PDF_SKILL.encode()).status_code == 409
    replaced = upload(admin, "SKILL.md", PDF_SKILL.replace("Use when handling PDFs.", "Updated."), replace=True)
    assert replaced.status_code == 200
    assert replaced.json()["skill"]["description"].endswith("Updated.")

    detail = admin.get(f"/api/skills/{skill['id']}").json()["skill"]
    assert detail["body"].startswith("# PDF Processing")
    assert detail["resources"] == []

    assert [s["name"] for s in member.get("/api/skills/enabled").json()["skills"]] == ["pdf-processing"]
    assert admin.patch(f"/api/skills/{skill['id']}/toggle").json()["is_enabled"] is False
    assert member.get("/api/skills/enabled").json()["skills"] == []

    assert admin.delete(f"/api/skills/{skill['id']}").status_code == 200
    assert admin.get("/api/skills").json()["total"] == 0
    assert not (skills_dir / "pdf-processing").exists()


def test_detail_hides_load_error_details(skills_dir):
    admin = client_for(ADMIN_USER)
    skill = upload(admin, "SKILL.md", PDF_SKILL.encode()).json()["skill"]
    (skills_dir / "pdf-processing" / "SKILL.md").write_text("broken without frontmatter", encoding="utf-8")
    detail = admin.get(f"/api/skills/{skill['id']}").json()["skill"]
    assert detail["body"] is None
    assert "錯誤代碼" in detail["load_error"]
    assert "frontmatter" not in detail["load_error"]


def test_admin_uploads_skill_folder(skills_dir):
    admin = client_for(ADMIN_USER)
    response = upload_folder(admin, PDF_FOLDER + [("pdf-processing/.git/HEAD", b"ref")])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message"] == "已安裝技能「pdf-processing」"
    assert [skill["name"] for skill in body["skills"]] == ["pdf-processing"]
    assert body["skipped"] == []
    assert (skills_dir / "pdf-processing" / "references" / "REFERENCE.md").read_text(encoding="utf-8") == "參考內容"
    assert not (skills_dir / "pdf-processing" / ".git").exists()

    conflict = upload_folder(admin, PDF_FOLDER)
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "已存在同名技能：pdf-processing"
    replaced = upload_folder(admin, PDF_FOLDER[:1], replace=True)
    assert replaced.status_code == 200
    assert replaced.json()["message"] == "已更新技能「pdf-processing」"
    assert not (skills_dir / "pdf-processing" / "references").exists()

    invalid = upload_folder(admin, [("demo/SKILL.md", b"---\nname: demo\n---\n")])
    assert invalid.status_code == 400
    assert "description" in invalid.json()["detail"]

    assert upload_folder(client_for(NORMAL_USER), PDF_FOLDER).status_code == 403


def test_admin_uploads_folder_of_skills(skills_dir):
    admin = client_for(ADMIN_USER)
    assert upload_folder(admin, [("skills/alpha/SKILL.md", skill_md("alpha"))]).status_code == 200
    collection = [
        ("skills/alpha/SKILL.md", skill_md("alpha", "Updated alpha.")),
        ("skills/beta/SKILL.md", skill_md("beta")),
        ("skills/beta/references/notes.md", b"notes"),
        ("skills/copy/SKILL.md", skill_md("beta")),
        ("skills/broken/SKILL.md", b"no frontmatter"),
    ]
    response = upload_folder(admin, collection)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message"] == "已安裝 1 個技能，略過 3 個"
    assert [skill["name"] for skill in body["skills"]] == ["beta"]
    skipped = {entry["path"]: entry for entry in body["skipped"]}
    assert skipped["skills/alpha"]["conflict"] is True
    assert skipped["skills/copy"] == {"path": "skills/copy", "reason": "與資料夾中其他技能同名：beta", "conflict": False}
    assert "frontmatter" in skipped["skills/broken"]["reason"]
    assert (skills_dir / "beta" / "references" / "notes.md").read_bytes() == b"notes"

    replaced = upload_folder(admin, collection[:3], replace=True).json()
    assert replaced["message"] == "已更新 2 個技能"
    assert {skill["name"]: skill["description"] for skill in replaced["skills"]}["alpha"] == "Updated alpha."

    none_installed = upload_folder(admin, collection[:3])
    assert none_installed.status_code == 409
    assert none_installed.json()["detail"].startswith("沒有安裝任何技能：skills/alpha：已存在同名技能：alpha；")

    names = sorted(skill["name"] for skill in admin.get("/api/skills").json()["skills"])
    assert names == ["alpha", "beta"]


def test_folder_upload_counts_skipped_files_toward_size_limit(skills_dir, monkeypatch):
    monkeypatch.setattr(skills_api, "MAX_SKILL_UNCOMPRESSED_BYTES", 1024)
    response = upload_folder(client_for(ADMIN_USER), PDF_FOLDER + [
        ("pdf-processing/.git/pack", b"x" * 700),
        ("pdf-processing/references/big.txt", b"y" * 300),
    ])
    assert response.status_code == 400
    assert "MiB" in response.json()["detail"]
    assert not (skills_dir / "pdf-processing").exists()


def test_folder_upload_reports_too_many_files(skills_dir, monkeypatch):
    monkeypatch.setattr(skills_api, "MAX_SKILL_FOLDER_FILES", 2)
    response = upload_folder(client_for(ADMIN_USER), PDF_FOLDER + [("pdf-processing/extra.md", b"x")])
    assert response.status_code == 400
    assert response.json()["detail"] == "無法讀取上傳的資料夾，一次最多 2 個檔案"
    assert not (skills_dir / "pdf-processing").exists()


def test_concurrent_uploads_keep_record_and_files_in_sync(skills_dir, monkeypatch):
    real_install = skills_api.install_skill

    def slow_install(*args, **kwargs):
        time.sleep(0.2)
        real_install(*args, **kwargs)

    monkeypatch.setattr(skills_api, "install_skill", slow_install)
    versions = [PDF_SKILL.replace("Use when handling PDFs.", f"Version {n}.").encode() for n in (1, 2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda data: upload(client_for(ADMIN_USER), "SKILL.md", data, replace=True), versions))
    assert [response.status_code for response in responses] == [200, 200]
    [record] = client_for(ADMIN_USER).get("/api/skills").json()["skills"]
    assert record["description"] in (skills_dir / "pdf-processing" / "SKILL.md").read_text(encoding="utf-8")


def test_upload_reports_invalid_skill(skills_dir):
    response = upload(client_for(ADMIN_USER), "SKILL.md", b"---\nname: demo\n---\n")
    assert response.status_code == 400
    assert "description" in response.json()["detail"]


def install_via_api(skills_dir):
    response = upload(client_for(ADMIN_USER), "pdf.zip", make_zip({"SKILL.md": PDF_SKILL, "references/REFERENCE.md": "ref"}))
    assert response.status_code == 200, response.text
    return response.json()["skill"]


def tool(tools_def, name):
    return next((t for t in tools_def if t["function"]["name"] == name), None)


@pytest.mark.asyncio
async def test_registry_exposes_skill_tools_only_when_enabled(skills_dir):
    registry = ResearchToolRegistry()
    assert tool(registry.get_tool_definitions(), "activate_skill") is None

    skill = install_via_api(skills_dir)
    tools_def = registry.get_tool_definitions()
    activate = tool(tools_def, "activate_skill")
    assert activate["function"]["parameters"]["properties"]["name"]["enum"] == ["pdf-processing"]
    assert "<name>pdf-processing</name>" in activate["function"]["description"]
    assert tool(tools_def, "read_skill_resource") is not None
    assert registry.approval_requirement("activate_skill") is None

    result = await registry.execute_tool("activate_skill", {"name": "pdf-processing"})
    assert result["content"].startswith("<skill_content")
    resource = await registry.execute_tool("read_skill_resource", {"skill": "pdf-processing", "path": "references/REFERENCE.md"})
    assert "ref" in resource["content"]

    client_for(ADMIN_USER).patch(f"/api/skills/{skill['id']}/toggle")
    assert tool(registry.get_tool_definitions(), "activate_skill") is None
    assert "error" in await registry.execute_tool("activate_skill", {"name": "pdf-processing"})


def test_session_passes_skill_content_unwrapped_and_deduplicates():
    session = ResearchSession([])
    output = {"skill": "pdf-processing", "content": '<skill_content name="pdf-processing">x</skill_content>'}
    assert session.tool_message_content("activate_skill", output) == output["content"]
    assert session.tool_message_content("activate_skill", {"error": "x"}).startswith("<untrusted_tool_result")
    assert session.tool_message_content("search_knowledge_base", output).startswith("<untrusted_tool_result")
    assert session.refuse_tool_call("activate_skill", {"name": "pdf-processing"}) is None
    session.record_tool_output("activate_skill", output)
    assert "已在本次提問載入" in session.refuse_tool_call("activate_skill", {"name": "pdf-processing"})["message"]


@pytest.mark.asyncio
async def test_slash_command_activates_skill_before_model_call(skills_dir):
    install_via_api(skills_dir)
    captured = {}

    async def fake_chat_completion(messages, **kwargs):
        captured["messages"] = messages
        return {"role": "assistant", "content": "完成"}

    agent = ResearchAgent(tool_registry=ResearchToolRegistry())
    with patch("app.rag.agent.chat_completion", fake_chat_completion):
        events = [e async for e in research(agent, "/pdf-processing 幫我整理這份 PDF")]

    system = captured["messages"][0]["content"]
    assert "[技能規則]" in system
    assert "本系統不會執行技能內的腳本" in system
    assert '<skill_content name="pdf-processing">' in system
    assert captured["messages"][-1]["content"] == "幫我整理這份 PDF"
    done = events[-1]["data"]
    assert done["research_trace"][0]["tool"] == "activate_skill"
    assert done["research_trace"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_unknown_slash_command_is_left_as_is(skills_dir):
    captured = {}

    async def fake_chat_completion(messages, **kwargs):
        captured["messages"] = messages
        return {"role": "assistant", "content": "完成"}

    agent = ResearchAgent(tool_registry=ResearchToolRegistry())
    with patch("app.rag.agent.chat_completion", fake_chat_completion):
        [e async for e in research(agent, "/unknown 你好")]

    assert "[技能規則]" not in captured["messages"][0]["content"]
    assert captured["messages"][-1]["content"] == "/unknown 你好"
