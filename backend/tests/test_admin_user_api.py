"""
管理後台的使用者端點
驗證：
1. 使用者清單與更新回應只含 UserProfile 欄位，不帶 hashed_password
2. 變更權限、帳號狀態與刪除使用者時寫入安全日誌，記錄操作的管理員
"""
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import admin as admin_api
from app.core.jwt_auth import get_current_admin_user
from app.models import User
from app.models.database import Base, get_db


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        session.add(User(
            username="member",
            email="member@example.com",
            hashed_password="$argon2id$v=19$m=65536,t=3,p=4$secret-hash",
            is_active=True,
            is_admin=False,
            role="user",
            created_at=datetime.utcnow(),
            tokens_valid_after=datetime.utcnow(),
        ))
        session.commit()

    def override_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app = FastAPI()
    app.include_router(admin_api.router, prefix="/api/admin")
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_admin_user] = lambda: {"user_id": 99, "username": "root", "is_admin": True}
    yield TestClient(app)
    engine.dispose()


def test_user_list_and_update_do_not_expose_password_hashes(client):
    listed = client.get("/api/admin/users")
    assert listed.status_code == 200
    assert listed.json()[0]["username"] == "member"
    assert "hashed_password" not in listed.text

    updated = client.put(f"/api/admin/users/{listed.json()[0]['id']}", json={"is_admin": True})
    assert updated.status_code == 200
    assert updated.json()["user"]["is_admin"] is True
    assert "hashed_password" not in updated.text


def test_admin_changes_are_audited(client, monkeypatch):
    events = []
    monkeypatch.setattr(admin_api, "log_security_event", lambda event, **kwargs: events.append((event, kwargs)))
    user_id = client.get("/api/admin/users").json()[0]["id"]

    client.put(f"/api/admin/users/{user_id}", json={"is_admin": True, "email": "member@example.com"})
    event, kwargs = events[-1]
    assert event == "ADMIN_USER_UPDATED"
    assert kwargs["user_id"] == 99
    assert kwargs["details"] == {"target_user_id": user_id, "changes": {"is_admin": {"from": False, "to": True}}}

    # 沒有實際變更時不寫日誌
    client.put(f"/api/admin/users/{user_id}", json={"is_admin": True})
    assert len(events) == 1

    assert client.delete(f"/api/admin/users/{user_id}").status_code == 200
    event, kwargs = events[-1]
    assert event == "ADMIN_USER_DELETED"
    assert kwargs["details"] == {"target_user_id": user_id, "username": "member", "was_admin": True}
