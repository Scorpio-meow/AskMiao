import json
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.api import chat as chat_api
from app.core.config import settings
from app.models import ConversationFile, Conversation, FileAttachment, LlmConnection, Message, MessageCreate
from app.models.database import Base
from app.rag import agent as agent_module
from app.rag.agent import ResearchAgent
from app.rag.tools import ResearchToolRegistry
from app.services import chat_service as chat_service_module
from app.services.agent_instructions import set_instructions
from app.services.chat_service import ChatService, _build_message_response
from app import prompts
@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chat.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()
def add_conversation(db, turns):
    conversation = Conversation(user_id=1, title="歷史測試")
    db.add(conversation)
    db.commit()
    for is_user, content in turns:
        db.add(Message(conversation_id=conversation.id, content=content, is_user=is_user))
    db.commit()
    return conversation
def add_connection(db):
    connection = LlmConnection(name="本機", provider="ollama", api_base="https://ollama.example.com",
                               models=json.dumps(["qwen3:8b"]), owner_id=1)
    db.add(connection)
    db.commit()
    return connection.id
async def send(db, connection_id, content, conversation_id=None, attachments=()):
    response = await chat_api.send_message(
        MessageCreate(content=content, conversation_id=conversation_id, connection_id=connection_id,
                      model_name="qwen3:8b", attachments=list(attachments)),
        db=db,
        user_id=1,
    )
    return "".join([chunk async for chunk in response.body_iterator])
def test_recent_history_starts_with_user_and_excludes_current_message(db):
    conversation = add_conversation(db, [
        (True, "q1"), (False, "a1"), (True, "q2"), (False, "a2"), (True, "current"),
    ])
    current = db.query(Message).filter(Message.content == "current").one()
    history = ChatService().get_recent_history(db, conversation.id, before_message_id=current.id, limit=3)
    assert history == [
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ]
@pytest.mark.asyncio
async def test_send_message_passes_database_history_to_rag(db, monkeypatch):
    conversation_id = add_conversation(db, [(True, "特休有幾天？"), (False, "依年資計算。")]).id
    captured = {}
    class FakeRag:
        async def generate_response_stream(self, query, conversation_history, *, endpoint, model_name,
                                           reasoning_effort=None, attachments=None, approval_user_id=None, conversation_id=None, mode, instructions):
            captured["mode"] = mode
            captured["instructions"] = instructions
            captured["endpoint"] = endpoint
            captured["model_name"] = model_name
            captured["query"] = query
            captured["history"] = conversation_history
            yield {"event": "token", "data": {"content": "滿一年七天。"}}
            yield {"event": "done", "data": {"answer": "滿一年七天。", "sources": []}}
    monkeypatch.setattr(settings, "CONVERSATION_HISTORY_MESSAGES", 6)
    monkeypatch.setattr(chat_api, "get_rag_system", lambda: FakeRag())
    connection = LlmConnection(name="本機", provider="ollama", api_base="https://ollama.example.com",
                               models=json.dumps(["qwen3:8b"]), owner_id=1)
    db.add(connection)
    db.commit()
    response = await chat_api.send_message(
        MessageCreate(content="那滿一年呢？", conversation_id=conversation_id, connection_id=connection.id, model_name="qwen3:8b"),
        db=db,
        user_id=1,
    )
    body = "".join([chunk async for chunk in response.body_iterator])
    assert (captured["mode"], captured["instructions"]) == ("research", "")
    assert captured["query"] == "那滿一年呢？"
    assert (captured["endpoint"].api_base, captured["model_name"]) == ("https://ollama.example.com", "qwen3:8b")
    assert captured["history"] == [
        {"role": "user", "content": "特休有幾天？"},
        {"role": "assistant", "content": "依年資計算。"},
    ]
    assert "event: done" in body
    assert db.query(Message).filter(Message.conversation_id == conversation_id).count() == 4
@pytest.mark.asyncio
async def test_send_message_saves_and_returns_the_final_answer_of_the_rag_stream(db, monkeypatch):
    conversation_id = add_conversation(db, []).id
    class FakeRag:
        async def generate_response_stream(self, query, conversation_history, **kwargs):
            yield {"event": "token", "data": {"content": "依年資計算 [3]。"}}
            yield {"event": "done", "data": {"answer": "依年資計算。", "sources": []}}
    monkeypatch.setattr(chat_api, "get_rag_system", lambda: FakeRag())
    connection = LlmConnection(name="本機", provider="ollama", api_base="https://ollama.example.com",
                               models=json.dumps(["qwen3:8b"]), owner_id=1)
    db.add(connection)
    db.commit()
    response = await chat_api.send_message(
        MessageCreate(content="特休怎麼算", conversation_id=conversation_id, connection_id=connection.id, model_name="qwen3:8b"),
        db=db,
        user_id=1,
    )
    body = "".join([chunk async for chunk in response.body_iterator])
    saved = db.query(Message).filter(Message.conversation_id == conversation_id, Message.is_user.is_(False)).one()
    assert saved.content == "依年資計算。"
    done_line = next(line for line in body.split("\n\n") if line.startswith("event: done"))
    assert json.loads(done_line.split("data: ", 1)[1])["answer"] == "依年資計算。"
def test_recent_history_attachment_text_is_bounded_from_the_newest(db, monkeypatch):
    monkeypatch.setattr(chat_service_module, "MAX_HISTORY_ATTACHMENT_CHARS", 6)
    conversation = add_conversation(db, [])
    for content, text in (("q1", "舊附件內容"), ("q2", "新附件內容很長")):
        context = json.dumps({"attachments": [{"filename": "a.txt", "file_type": "text/plain", "content": text}]}, ensure_ascii=False)
        db.add(Message(conversation_id=conversation.id, content=content, is_user=True, context_used=context))
    current = Message(conversation_id=conversation.id, content="current", is_user=True)
    db.add(current)
    db.commit()
    history = ChatService().get_recent_history(db, conversation.id, before_message_id=current.id, limit=10)
    assert history == [
        {"role": "user", "content": "q1"},
        {"role": "user", "content": "[附件：a.txt]\n新附件內容很\n\n[使用者問題]\nq2"},
    ]
@pytest.mark.asyncio
async def test_follow_up_question_sees_earlier_attachment_text(db, monkeypatch):
    registry = ResearchToolRegistry()
    monkeypatch.setattr(registry, "get_tool_definitions", lambda user_id=None, conversation_id=None, requested_skill=None: [])
    agent = ResearchAgent(tool_registry=registry)
    sent = []
    async def fake_chat_completion(messages, **kwargs):
        sent.append(messages)
        return {"role": "assistant", "content": "好"}
    class AgentRag:
        def generate_response_stream(self, query, conversation_history, **kwargs):
            return agent.stream_research(query, conversation_history=conversation_history, **kwargs)
    monkeypatch.setattr(agent_module, "chat_completion", fake_chat_completion)
    monkeypatch.setattr(agent_module, "_extract_attachment_text", lambda fname, ftype, url, ocr: "特休依年資計算")
    monkeypatch.setattr(agent_module, "_attachment_ocr", lambda: None)
    now = datetime(2026, 11, 8, 23, 7, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr(agent_module, "local_now", lambda: now)
    monkeypatch.setattr(settings, "CONVERSATION_HISTORY_MESSAGES", 6)
    monkeypatch.setattr(chat_api, "get_rag_system", lambda: AgentRag())
    connection_id = add_connection(db)
    attachment = FileAttachment(filename="規章.txt", file_type="text/plain", data_url="data:text/plain;base64,QUFBQQ==")
    await send(db, connection_id, "摘要附件", attachments=[attachment])
    await send(db, connection_id, "那病假呢？", conversation_id=db.query(Conversation).one().id)
    file_id = db.query(ConversationFile).one().id
    assert sent[-1][1:] == [
        {"role": "user", "content": f"[附件 #{file_id}：規章.txt]\n特休依年資計算\n\n[使用者問題]\n摘要附件"},
        {"role": "assistant", "content": "好"},
        {"role": "user", "content": agent_module.with_current_time("那病假呢？", now)},
    ]
@pytest.mark.asyncio
async def test_answer_is_not_saved_when_conversation_is_deleted_mid_stream(db, monkeypatch):
    class DeletingRag:
        async def generate_response_stream(self, query, conversation_history, **kwargs):
            ChatService().delete_conversation(db, db.query(Conversation).one().id, 1)
            yield {"event": "token", "data": {"content": "回答"}}
            yield {"event": "done", "data": {"answer": "回答", "sources": []}}
    monkeypatch.setattr(chat_api, "get_rag_system", lambda: DeletingRag())
    body = await send(db, add_connection(db), "問題")
    assert '"message_id": null' in body
    assert (db.query(Conversation).count(), db.query(Message).count()) == (0, 0)
@pytest.mark.asyncio
async def test_agent_mode_streams_and_saves_the_plan(db, monkeypatch):
    plan = [{"step": "查規定", "status": "completed"}, {"step": "寫報告", "status": "in_progress"}]
    captured = {}
    class PlanningRag:
        async def generate_response_stream(self, query, conversation_history, *, mode, **kwargs):
            captured["mode"] = mode
            yield {"event": "plan", "data": {"items": plan}}
            yield {"event": "done", "data": {"answer": "完成", "sources": [], "plan": plan}}
    monkeypatch.setattr(chat_api, "get_rag_system", lambda: PlanningRag())
    response = await chat_api.send_message(
        MessageCreate(content="整理規定", connection_id=add_connection(db), model_name="qwen3:8b", mode="agent"),
        db=db,
        user_id=1,
    )
    body = "".join([chunk async for chunk in response.body_iterator])
    assert captured["mode"] == "agent"
    assert f"event: plan\ndata: {json.dumps({'items': plan}, ensure_ascii=False)}" in body
    saved = db.query(Message).filter(Message.is_user.is_(False)).one()
    assert _build_message_response(saved).plan == plan
def test_unknown_chat_mode_is_rejected():
    with pytest.raises(ValueError):
        MessageCreate(content="hi", connection_id=1, model_name="qwen3:8b", mode="autopilot")
@pytest.mark.asyncio
async def test_send_message_passes_organization_and_personal_instructions(db, monkeypatch):
    set_instructions(db, None, "  回答附上負責單位  ")
    set_instructions(db, 1, "先列重點")
    set_instructions(db, 2, "別人的偏好")
    captured = {}
    class InstructedRag:
        async def generate_response_stream(self, query, conversation_history, *, instructions, **kwargs):
            captured["instructions"] = instructions
            yield {"event": "done", "data": {"answer": "好", "sources": []}}
    monkeypatch.setattr(chat_api, "get_rag_system", lambda: InstructedRag())
    await send(db, add_connection(db), "整理規定")
    assert captured["instructions"] == (
        prompts.ORGANIZATION_INSTRUCTIONS.format(content="回答附上負責單位")
        + prompts.PERSONAL_INSTRUCTIONS.format(content="先列重點")
    )
    set_instructions(db, 1, "   ")
    set_instructions(db, None, "")
    await send(db, add_connection(db), "再問一次")
    assert captured["instructions"] == ""