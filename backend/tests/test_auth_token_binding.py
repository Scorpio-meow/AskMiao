"""
存取權杖與帳號的綁定
驗證：
1. 只接受以 RSA 私鑰簽署的 RS256 權杖，沒有可用共用密鑰偽造的 HS256 路徑
2. 身分與管理員權限取自資料庫，不信任權杖內的 is_admin 等聲明
3. 帳號刪除、停用，或權杖簽發早於帳號建立（id 被重用）時權杖立即失效
4. SQLite 的 users 表以 AUTOINCREMENT 建立，刪除後的 id 不會配給新帳號
5. 變更密碼後，先前簽發的存取與重新整理權杖一律失效；既有資料庫補上 tokens_valid_after
"""
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from app.core import jwt_auth
from app.core.jwt_auth import (
    TokenManager,
    create_token_pair,
    get_current_user_from_token,
    resolve_token_user,
    verify_refresh_token,
)
from app.crud import crud_user
from app.models import User
from app.models.database import Base, upgrade_schema


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def add_user(db, username, *, is_admin=False):
    created_at = datetime.utcnow() - timedelta(minutes=5)
    user = User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="x",
        is_active=True,
        is_admin=is_admin,
        role="admin" if is_admin else "user",
        created_at=created_at,
        tokens_valid_after=created_at,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db, token):
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    return get_current_user_from_token(credentials=credentials, db=db)


def access_token_for(user, **claims):
    data = {"user_id": user.id, "username": user.username, "email": user.email, "role": user.role, "is_admin": user.is_admin}
    data.update(claims)
    return create_token_pair(data)["access_token"]


def assert_rejected(db, token):
    with pytest.raises(HTTPException) as exc_info:
        authenticate(db, token)
    assert exc_info.value.status_code == 401


def test_module_has_no_shared_secret_fallback():
    assert jwt_auth.ALGORITHM == "RS256"
    assert not hasattr(jwt_auth, "SECRET_KEY")
    assert not hasattr(jwt_auth, "USE_RSA")


def test_hs256_token_is_rejected(db):
    user = add_user(db, "member")
    now = datetime.utcnow()
    for key in ("your_jwt_secret_key_here", jwt_auth.RSA_PUBLIC_KEY):
        try:
            forged = jwt.encode(
                {"sub": str(user.id), "type": "access", "is_admin": True, "iat": now, "exp": now + timedelta(minutes=5)},
                key,
                algorithm="HS256",
            )
        except Exception:
            # jose 拒絕以 PEM 公鑰當 HMAC 密鑰時，本身就無法偽造
            continue
        assert_rejected(db, forged)


def test_admin_claim_comes_from_database(db):
    user = add_user(db, "member")
    token = access_token_for(user, is_admin=True, role="admin", username="someone-else")
    current = authenticate(db, token)
    assert current == {
        "user_id": user.id,
        "username": "member",
        "email": "member@example.com",
        "role": "user",
        "is_admin": False,
    }


def test_demoted_admin_loses_access_immediately(db):
    admin = add_user(db, "boss", is_admin=True)
    token = access_token_for(admin)
    assert authenticate(db, token)["is_admin"] is True
    admin.is_admin = False
    db.commit()
    assert authenticate(db, token)["is_admin"] is False


def test_deleted_or_inactive_user_token_is_rejected(db):
    deleted = add_user(db, "gone")
    deleted_token = access_token_for(deleted)
    db.delete(deleted)
    db.commit()
    assert_rejected(db, deleted_token)

    inactive = add_user(db, "paused")
    inactive_token = access_token_for(inactive)
    inactive.is_active = False
    db.commit()
    assert_rejected(db, inactive_token)


def test_token_issued_before_account_creation_is_rejected(db):
    user = add_user(db, "reused")
    stale_token = access_token_for(user)
    # 模擬同一 id 在權杖簽發後才重新建立的帳號（建立帳號時 tokens_valid_after 等於 created_at）
    user.created_at = user.tokens_valid_after = datetime.utcnow() + timedelta(seconds=5)
    db.commit()
    assert_rejected(db, stale_token)


def frozen_utcnow(moment):
    return type("FrozenDatetime", (datetime,), {"utcnow": classmethod(lambda cls: moment)})


def test_password_change_revokes_previously_issued_tokens(db, monkeypatch):
    user = add_user(db, "member")
    tokens = create_token_pair({"user_id": user.id, "username": user.username})
    assert authenticate(db, tokens["access_token"])["user_id"] == user.id

    changed_at = datetime.utcnow() + timedelta(minutes=1)
    monkeypatch.setattr(crud_user, "datetime", frozen_utcnow(changed_at))
    crud_user.update_user_password(db, user.id, "NewSecret123")
    assert user.tokens_valid_after == changed_at
    assert_rejected(db, tokens["access_token"])
    with pytest.raises(HTTPException) as exc_info:
        resolve_token_user(db, verify_refresh_token(tokens["refresh_token"]))
    assert exc_info.value.status_code == 401

    # 變更之後才簽發的權杖照常有效
    monkeypatch.setattr(jwt_auth, "datetime", frozen_utcnow(changed_at + timedelta(seconds=1)))
    fresh = create_token_pair({"user_id": user.id, "username": user.username})
    assert authenticate(db, fresh["access_token"])["user_id"] == user.id


def test_new_accounts_start_with_tokens_valid_after_creation(db):
    user = crud_user.create_user(db, "newbie", "newbie@example.com", "Secret123")
    assert user.tokens_valid_after == user.created_at


def test_existing_users_table_gets_tokens_valid_after_backfill(tmp_path):
    old = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR, created_at DATETIME)"))
        conn.execute(text("INSERT INTO users (username, created_at) VALUES ('legacy', '2026-01-02 03:04:05')"))
    upgrade_schema(old)
    upgrade_schema(old)
    with old.connect() as conn:
        assert conn.execute(text("SELECT tokens_valid_after FROM users")).scalar() == "2026-01-02 03:04:05"
    old.dispose()


def test_refresh_token_cannot_be_used_as_access_token(db):
    user = add_user(db, "member")
    refresh = TokenManager.create_refresh_token({"sub": str(user.id)})
    assert_rejected(db, refresh)


def test_sqlite_users_table_uses_autoincrement(db):
    from sqlalchemy.dialects import sqlite

    ddl = str(CreateTable(User.__table__).compile(dialect=sqlite.dialect()))
    assert "AUTOINCREMENT" in ddl
    first = add_user(db, "first")
    second = add_user(db, "second")
    deleted_id = second.id
    db.delete(second)
    db.commit()
    third = add_user(db, "third")
    assert third.id > deleted_id > first.id
