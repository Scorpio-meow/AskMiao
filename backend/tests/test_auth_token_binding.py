"""
存取權杖與帳號的綁定
驗證：
1. 只接受以 RSA 私鑰簽署的 RS256 權杖：以共用字串或伺服器公鑰（PEM 或 DER）當 HMAC 密鑰偽造的 HS256 權杖一律拒絕
2. 身分與管理員權限取自資料庫，不信任權杖內的 is_admin 等聲明
3. 帳號刪除、停用，或權杖簽發早於帳號建立（id 被重用）時權杖立即失效
4. SQLite 的 users 表以 AUTOINCREMENT 建立，刪除後的 id 不會配給新帳號
5. 變更密碼後，先前簽發的存取與重新整理權杖一律失效（同一秒內稍早簽發的也是）；既有資料庫補上 tokens_valid_after，
   回退到舊版期間建立、此欄位為 NULL 的帳號在每次啟動時補值
6. 撤銷的權杖保留到原本的到期時間，與伺服器的時區無關
"""
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
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
    revoke_token,
    verify_refresh_token,
)
from app.core.redis_client import TokenBlacklist
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


def forge_hs256(claims, key: bytes) -> str:
    """攻擊者自行計算 HMAC 簽出的 HS256 權杖，不經過任何 JWT 函式庫的金鑰檢查"""
    def encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    signing_input = f"{encode(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())}.{encode(json.dumps(claims).encode())}"
    signature = hmac.new(key, signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{encode(signature)}"


def test_hs256_token_is_rejected(db):
    # 演算法混淆：以 HS256 冒充 RS256，HMAC 密鑰用共用字串或伺服器的公鑰。python-jose 3.5.0 會把不含 PEM 外框的
    # DER 公鑰當成 HMAC 密鑰（CVE-2024-33663 的修正不完整）；驗證端只接受 RS256，這些權杖一律無效
    user = add_user(db, "member")
    now = int(time.time())
    claims = {"sub": str(user.id), "type": "access", "is_admin": True, "iat": now, "exp": now + 300}
    public_pem = jwt_auth.RSA_PUBLIC_KEY.encode("ascii")
    public_der = serialization.load_pem_public_key(public_pem).public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    for key in (b"a-shared-secret-that-was-never-configured", public_pem, public_der):
        assert_rejected(db, forge_hs256(claims, key))


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
    # 時間都放在過去：簽發時間在未來的權杖本身就會被拒絕
    user = add_user(db, "member")
    issued_at = datetime.utcnow() - timedelta(minutes=3)
    monkeypatch.setattr(jwt_auth, "datetime", frozen_utcnow(issued_at))
    tokens = create_token_pair({"user_id": user.id, "username": user.username})
    assert authenticate(db, tokens["access_token"])["user_id"] == user.id

    changed_at = issued_at + timedelta(minutes=1)
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


def test_tokens_from_the_same_second_as_a_password_change_are_revoked(db, monkeypatch):
    user = add_user(db, "member")
    second = datetime.utcnow().replace(microsecond=0) - timedelta(minutes=1)
    monkeypatch.setattr(jwt_auth, "datetime", frozen_utcnow(second.replace(microsecond=100_000)))
    earlier = create_token_pair({"user_id": user.id, "username": user.username})

    monkeypatch.setattr(crud_user, "datetime", frozen_utcnow(second.replace(microsecond=600_000)))
    crud_user.update_user_password(db, user.id, "NewSecret123")
    assert_rejected(db, earlier["access_token"])
    with pytest.raises(HTTPException) as exc_info:
        resolve_token_user(db, verify_refresh_token(earlier["refresh_token"]))
    assert exc_info.value.status_code == 401

    # 同一秒內、變更之後簽發的權杖照常有效（例如立刻以新密碼重新登入）
    monkeypatch.setattr(jwt_auth, "datetime", frozen_utcnow(second.replace(microsecond=900_000)))
    later = create_token_pair({"user_id": user.id, "username": user.username})
    assert authenticate(db, later["access_token"])["user_id"] == user.id


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


def test_accounts_created_without_tokens_valid_after_are_backfilled_on_every_start(tmp_path):
    # 升級後回退到舊版再升級：欄位已存在，舊版建立的帳號此欄位為 NULL，所有權杖都會被拒絕
    old = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR, created_at DATETIME, "
                          "tokens_valid_after DATETIME)"))
        conn.execute(text("INSERT INTO users (username, created_at, tokens_valid_after) VALUES "
                          "('upgraded', '2026-01-02 03:04:05', '2026-05-06 07:08:09'), "
                          "('created-by-old-version', '2026-03-04 05:06:07', NULL)"))
    upgrade_schema(old)
    with old.connect() as conn:
        rows = dict(conn.execute(text("SELECT username, tokens_valid_after FROM users")).all())
    assert rows == {"upgraded": "2026-05-06 07:08:09", "created-by-old-version": "2026-03-04 05:06:07"}
    old.dispose()


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="需要 time.tzset 切換時區")
@pytest.mark.parametrize("zone", ["UTC", "Asia/Taipei", "America/Los_Angeles"])
def test_revocation_lasts_until_the_token_expires_in_any_timezone(monkeypatch, zone):
    monkeypatch.setenv("TZ", zone)
    time.tzset()
    try:
        token = TokenManager.create_access_token({"sub": "1"}, expires_delta=timedelta(minutes=30))
        assert revoke_token(token)
        expires_at = TokenBlacklist._blacklist[TokenBlacklist._key(token)]
        assert abs(expires_at - (time.time() + 30 * 60)) < 5
    finally:
        monkeypatch.undo()
        time.tzset()


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
