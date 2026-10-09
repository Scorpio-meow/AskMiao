"""
自行註冊的開關與帳號建立腳本
驗證：
1. ALLOW_REGISTRATION 關閉時註冊回傳 403 且不建立帳號；開啟時照常註冊
2. GET /api/auth/registration 反映目前的設定
3. scripts/create_user.py 套用與註冊相同的規則，可建立管理員
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import auth as auth_api
from app.core.config import settings
from app.models import User
from app.models.database import Base, get_db
from scripts.create_user import create_account

NEW_USER = {"username": "newbie", "email": "newbie@example.com", "password": "Secret123"}


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    engine.dispose()


@pytest.fixture
def client(session_factory):
    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = FastAPI()
    app.include_router(auth_api.router)
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_registration_is_rejected_when_closed(client, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_REGISTRATION", False)
    assert client.get("/api/auth/registration").json() == {"enabled": False}
    response = client.post("/api/auth/register", json=NEW_USER)
    assert response.status_code == 403
    with session_factory() as session:
        assert session.query(User).count() == 0


def test_registration_works_when_open(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_REGISTRATION", True)
    assert client.get("/api/auth/registration").json() == {"enabled": True}
    response = client.post("/api/auth/register", json=NEW_USER)
    assert response.status_code == 201
    assert response.json()["user"]["is_admin"] is False


def test_create_account_script_applies_registration_rules(session_factory):
    with session_factory() as session:
        admin = create_account(session, "root", "root@example.com", "Secret123", is_admin=True)
        assert admin.is_admin is True and admin.role == "admin"
        assert admin.tokens_valid_after == admin.created_at
        member = create_account(session, "member", "member@example.com", "Secret123", is_admin=False)
        assert member.is_admin is False and member.role == "user"
        for username, email, password, message in (
            ("root", "other@example.com", "Secret123", "使用者名稱"),
            ("other", "root@example.com", "Secret123", "電子郵件"),
            ("weak", "weak@example.com", "alllowercase1", "大寫"),
            ("bad name", "bad@example.com", "Secret123", "使用者名稱"),
            ("short-pw", "short@example.com", "Ab1", "8"),
        ):
            with pytest.raises(ValueError, match=message):
                create_account(session, username, email, password, is_admin=False)
