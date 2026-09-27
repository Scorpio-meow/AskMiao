"""
存取權杖與帳號的綁定
驗證：
1. 只接受以 RSA 私鑰簽署的 RS256 權杖，沒有可用共用密鑰偽造的 HS256 路徑
2. 身分與管理員權限取自資料庫，不信任權杖內的 is_admin 等聲明
3. 帳號刪除、停用，或權杖簽發早於帳號建立（id 被重用）時權杖立即失效
4. SQLite 的 users 表以 AUTOINCREMENT 建立，刪除後的 id 不會配給新帳號
"""
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from app.core import jwt_auth
from app.core.jwt_auth import TokenManager, create_token_pair, get_current_user_from_token
from app.models import User
from app.models.database import Base


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


def add_user(db, username, *, is_admin=False, created_at=None):
    user = User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="x",
        is_active=True,
        is_admin=is_admin,
        role="admin" if is_admin else "user",
        created_at=created_at or datetime.utcnow() - timedelta(minutes=5),
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
    # 模擬同一 id 在權杖簽發後才重新建立的帳號
    user.created_at = datetime.utcnow() + timedelta(seconds=5)
    db.commit()
    assert_rejected(db, stale_token)


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
