import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import chat as chat_api
from app.core.config import settings
from app.models import Conversation, Message, MessageCreate
from app.models.database import Base
from app.services.chat_service import ChatService


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chat.db'}")
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
    conversation = add_conversation(db, [(True, "特休有幾天？"), (False, "依年資計算。")])
    captured = {}

    class FakeRag:
        async def generate_response_stream(self, query, conversation_history, model_name=None,
                                           reasoning_effort=None, attachments=None):
            captured["query"] = query
            captured["history"] = conversation_history
            yield {"event": "token", "data": {"content": "滿一年七天。"}}
            yield {"event": "done", "data": {"answer": "滿一年七天。", "sources": []}}

    monkeypatch.setattr(settings, "CONVERSATION_HISTORY_MESSAGES", 6)
    monkeypatch.setattr(chat_api, "get_rag_system", lambda: FakeRag())

    response = await chat_api.send_message(
        MessageCreate(content="那滿一年呢？", conversation_id=conversation.id),
        db=db,
        user_id=1,
    )
    body = "".join([chunk async for chunk in response.body_iterator])

    assert captured["query"] == "那滿一年呢？"
    assert captured["history"] == [
        {"role": "user", "content": "特休有幾天？"},
        {"role": "assistant", "content": "依年資計算。"},
    ]
    assert "event: done" in body
    assert db.query(Message).filter(Message.conversation_id == conversation.id).count() == 4
