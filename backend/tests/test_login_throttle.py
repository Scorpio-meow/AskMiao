"""
登入失敗節流
驗證：
1. 同一登入識別或同一來源位址在視窗內失敗達門檻後暫時鎖定，到期自動解除
2. 視窗外的失敗不計入；登入識別不分大小寫；成功登入清除該帳號的失敗紀錄
3. 登入路由在鎖定期間回傳 429 與 Retry-After，正確密碼也不會被接受，不洩漏密碼是否正確
4. 追蹤的鍵數有上限
5. 存取權杖過期時仍能登出並撤銷重新整理權杖；沒有 Authorization 標頭時不受理
"""
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import auth as auth_api
from app.core import login_throttle as throttle_module
from app.core.login_throttle import LoginThrottle
from app.crud import crud_user
from app.models.database import Base, get_db


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make_throttle(clock, *, per_account=3, per_address=5, window=60, lockout=300):
    return LoginThrottle(
        max_failures_per_account=per_account,
        max_failures_per_address=per_address,
        window_seconds=window,
        lockout_seconds=lockout,
        clock=clock,
    )


def test_account_is_locked_after_threshold_and_unlocks_after_lockout():
    clock = FakeClock()
    throttle = make_throttle(clock)
    for attempt in range(2):
        assert not throttle.record_failure("Alice", f"10.0.0.{attempt}")
    assert throttle.retry_after("alice", "10.0.0.9") == 0
    assert throttle.record_failure(" ALICE ", "10.0.0.3")
    assert throttle.retry_after("alice", "10.0.0.9") == 300
    clock.now += 299.5
    assert throttle.retry_after("alice", "10.0.0.9") == 1
    clock.now += 1
    assert throttle.retry_after("alice", "10.0.0.9") == 0
    # 其他帳號不受影響
    assert throttle.retry_after("bob", "10.0.0.9") == 0


def test_failures_outside_the_window_are_forgotten():
    clock = FakeClock()
    throttle = make_throttle(clock)
    throttle.record_failure("alice", "10.0.0.1")
    throttle.record_failure("alice", "10.0.0.1")
    clock.now += 61
    assert not throttle.record_failure("alice", "10.0.0.1")
    assert throttle.retry_after("alice", "10.0.0.1") == 0


def test_address_is_locked_across_accounts_and_success_only_clears_the_account():
    clock = FakeClock()
    throttle = make_throttle(clock, per_account=10, per_address=3)
    throttle.record_failure("alice", "203.0.113.5")
    throttle.record_success("alice")
    throttle.record_failure("bob", "203.0.113.5")
    assert throttle.record_failure("carol", "203.0.113.5")
    assert throttle.retry_after("dave", "203.0.113.5") == 300
    assert throttle.retry_after("dave", "203.0.113.6") == 0
    # 沒有來源位址時只依帳號計數
    assert throttle.retry_after("dave", None) == 0


def test_tracked_keys_are_bounded(monkeypatch):
    monkeypatch.setattr(throttle_module, "MAX_TRACKED_LOGIN_ACCOUNTS", 3)
    clock = FakeClock()
    throttle = make_throttle(clock, per_account=2)
    throttle.record_failure("victim", None)
    for index in range(3):
        throttle.record_failure(f"other-{index}", None)
    assert len(throttle._accounts._records) == 3
    assert "victim" not in throttle._accounts._records


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        crud_user.create_user(session, "member", "member@example.com", "Secret123")

    def override_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    clock = FakeClock()
    monkeypatch.setattr(auth_api, "login_throttle", make_throttle(clock))
    app = FastAPI()
    app.include_router(auth_api.router)
    app.dependency_overrides[get_db] = override_db
    yield TestClient(app), clock
    engine.dispose()


def test_login_route_returns_429_while_locked_even_with_the_right_password(client):
    http, clock = client
    for _ in range(3):
        assert http.post("/api/auth/login", json={"username": "member", "password": "wrong"}).status_code == 401
    locked = http.post("/api/auth/login", json={"username": "member", "password": "Secret123"})
    assert locked.status_code == 429
    assert locked.headers["Retry-After"] == "300"
    clock.now += 300
    assert http.post("/api/auth/login", json={"username": "member", "password": "Secret123"}).status_code == 200


def test_successful_login_resets_the_account_counter(client):
    http, _ = client
    for _ in range(2):
        http.post("/api/auth/login", json={"username": "member", "password": "wrong"})
    assert http.post("/api/auth/login", json={"username": "member", "password": "Secret123"}).status_code == 200
    for _ in range(2):
        assert http.post("/api/auth/login", json={"username": "member", "password": "wrong"}).status_code == 401
    assert http.post("/api/auth/login", json={"username": "member", "password": "Secret123"}).status_code == 200


def test_password_change_clears_the_refresh_cookie_and_ends_the_session(client, monkeypatch):
    http, _ = client
    login = http.post("/api/auth/login", json={"username": "member", "password": "Secret123"})
    access = login.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {access}"}
    later = datetime.utcnow().replace(microsecond=0)
    monkeypatch.setattr(crud_user, "datetime", type("Later", (datetime,), {
        "utcnow": classmethod(lambda cls: later.replace(year=later.year + 1)),
    }))
    changed = http.post("/api/auth/change-password", headers=headers, json={
        "current_password": "Secret123",
        "new_password": "Changed456",
        "confirm_password": "Changed456",
    })
    assert changed.status_code == 200
    assert 'refresh_token=""' in changed.headers["set-cookie"]
    assert http.get("/api/auth/me", headers=headers).status_code == 401


def test_logout_with_an_expired_access_token_revokes_the_refresh_cookie(client):
    from datetime import timedelta

    from app.core.jwt_auth import TokenManager
    from app.core.redis_client import TokenBlacklist

    http, _ = client
    login = http.post("/api/auth/login", json={"username": "member", "password": "Secret123"})
    refresh_cookie = login.cookies["refresh_token"]
    user_id = login.json()["user"]["id"]
    expired = TokenManager.create_access_token({"sub": str(user_id)}, expires_delta=timedelta(seconds=-60))

    assert http.post("/api/auth/logout").status_code in (401, 403)
    assert not TokenBlacklist.is_blacklisted(refresh_cookie)

    response = http.post("/api/auth/logout", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 200
    assert 'refresh_token=""' in response.headers["set-cookie"]
    assert TokenBlacklist.is_blacklisted(refresh_cookie)
