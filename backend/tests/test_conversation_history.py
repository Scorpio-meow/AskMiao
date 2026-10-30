import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import chat as chat_api
from app.core.config import settings
from app.models import Conversation, FileAttachment, LlmConnection, Message, MessageCreate
from app.models.database import Base
from app.rag import agent as agent_module
from app.rag.agent import ResearchAgent
from app.rag.tools import ResearchToolRegistry
from app.services import chat_service as chat_service_module
from app.services.chat_service import ChatService


@pytest.fixture
def db(tmp_path):
    # 聊天路由會在執行緒中使用同一個 Session，與正式環境的 SQLite 設定一致
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
                                           reasoning_effort=None, attachments=None, approval_user_id=None):
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

    assert captured["query"] == "那滿一年呢？"
    assert (captured["endpoint"].api_base, captured["model_name"]) == ("https://ollama.example.com", "qwen3:8b")
    assert captured["history"] == [
        {"role": "user", "content": "特休有幾天？"},
        {"role": "assistant", "content": "依年資計算。"},
    ]
    assert "event: done" in body
    assert db.query(Message).filter(Message.conversation_id == conversation_id).count() == 4


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
        {"role": "user", "content": "[附加檔案: a.txt]\n新附件內容很\n\n[使用者問題]\nq2"},
    ]


@pytest.mark.asyncio
async def test_follow_up_question_sees_earlier_attachment_text(db, monkeypatch):
    registry = ResearchToolRegistry()
    monkeypatch.setattr(registry, "get_tool_definitions", lambda user_id=None: [])
    agent = ResearchAgent(tool_registry=registry)
    sent = []

    async def fake_chat_completion(messages, **kwargs):
        sent.append(messages)
        return {"role": "assistant", "content": "好"}

    class AgentRag:
        def generate_response_stream(self, query, conversation_history, **kwargs):
            return agent.stream_research(query, conversation_history=conversation_history, **kwargs)

    monkeypatch.setattr(agent_module, "chat_completion", fake_chat_completion)
    monkeypatch.setattr(agent_module, "_extract_attachment_text", lambda fname, ftype, url: "特休依年資計算")
    monkeypatch.setattr(settings, "CONVERSATION_HISTORY_MESSAGES", 6)
    monkeypatch.setattr(chat_api, "get_rag_system", lambda: AgentRag())
    connection_id = add_connection(db)
    attachment = FileAttachment(filename="規章.txt", file_type="text/plain", data_url="data:text/plain;base64,QUFBQQ==")

    await send(db, connection_id, "摘要附件", attachments=[attachment])
    await send(db, connection_id, "那病假呢？", conversation_id=db.query(Conversation).one().id)

    assert sent[-1][1:] == [
        {"role": "user", "content": "[附加檔案: 規章.txt]\n特休依年資計算\n\n[使用者問題]\n摘要附件"},
        {"role": "assistant", "content": "好"},
        {"role": "user", "content": "那病假呢？"},
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
