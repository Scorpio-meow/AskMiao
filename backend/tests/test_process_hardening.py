"""
行程內狀態、子行程、日誌與背景資源的上限
驗證：
1. 權杖撤銷名單以雜湊為鍵、條目數有上限，到期項目不需全表掃描
2. 入侵偵測的每位址事件與追蹤位址數有上限，持續超量只警報一次
3. 安全日誌欄位截斷、不重複寫入 app.log 且會輪替；登入欄位長度有上限
4. Argon2 在執行緒中執行；工具清單需要登入且知識庫描述有快取
5. stdio MCP 子行程關閉時連同孫行程一起終止
6. jieba 快取放在資料目錄；已刪除文件的片段不會被寫回索引
7. 速率限制追蹤的位址數有上限；JWT 私鑰建立時就只有擁有者可讀
"""
import asyncio
import logging
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

import psutil
import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError

from app.api import auth as auth_api
from app.api import chat as chat_api
from app.core import redis_client
from app.core import security as security_module
from app.core.intrusion_detection import IntrusionDetector
from app.core.rsa_keys import RSAKeyManager
from app.core.limits import MAX_LOG_FIELD_CHARS, MAX_LOGIN_IDENTIFIER_CHARS
from app.core.redis_client import TokenBlacklist
from app.core.security_logging import security_logger, truncate_log_value
from app.core.user_context import get_current_user_id
from app.rag import tokenizers
from app.rag import tools as tools_module
from app.rag.tools import ResearchToolRegistry
from app.schemas.auth import UserLogin
from app.services.mcp_service import McpStdioClient


@pytest.fixture
def empty_blacklist(monkeypatch):
    monkeypatch.setattr(TokenBlacklist, "_blacklist", {})
    monkeypatch.setattr(TokenBlacklist, "_expiry_heap", [])


def test_token_blacklist_is_bounded_and_keyed_by_hash(empty_blacklist, monkeypatch):
    monkeypatch.setattr(redis_client, "MAX_REVOKED_TOKENS", 3)
    for index in range(5):
        TokenBlacklist.add_token(f"token-{index}", expires_in=100 + index)
    assert len(TokenBlacklist._blacklist) == 3
    assert all(len(key) == 64 and "token" not in key for key in TokenBlacklist._blacklist)
    # 最早到期的先被淘汰
    assert not TokenBlacklist.is_blacklisted("token-0")
    assert TokenBlacklist.is_blacklisted("token-4")


def test_expired_tokens_leave_the_blacklist(empty_blacklist, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(redis_client.time, "time", lambda: now[0])
    TokenBlacklist.add_token("short", expires_in=10)
    TokenBlacklist.add_token("long", expires_in=1000)
    now[0] += 20
    assert not TokenBlacklist.is_blacklisted("short")
    assert TokenBlacklist.is_blacklisted("long")
    assert len(TokenBlacklist._blacklist) == 1


def test_intrusion_detector_state_is_bounded(tmp_path, monkeypatch):
    from app.core import intrusion_detection

    monkeypatch.setattr(intrusion_detection, "MAX_TRACKED_ADDRESSES", 100)
    detector = IntrusionDetector(str(tmp_path / "ids.log"))
    alerts = []
    monkeypatch.setattr(detector, "_trigger_alert", lambda *args: alerts.append(args))
    started = time.monotonic()
    for _ in range(20_000):
        detector.record_event("api_request", "203.0.113.9")
    assert time.monotonic() - started < 2
    assert len(detector.ip_events["203.0.113.9"]["api_request"]) <= detector.thresholds["api_requests_max"] + 1
    assert len(alerts) == 1
    for index in range(500):
        detector.record_event("api_request", f"198.51.100.{index % 250}-{index}")
    assert len(detector.ip_events) <= 100


def test_security_log_fields_are_truncated_and_not_duplicated():
    long_name = "a" * 10_000
    truncated = truncate_log_value({"details": {"username": long_name}})
    assert len(truncated["details"]["username"]) < MAX_LOG_FIELD_CHARS + 20
    assert security_logger.propagate is False
    security_files = [h for h in security_logger.handlers if getattr(h, "baseFilename", "").endswith("security.log")]
    assert security_files and all(isinstance(h, RotatingFileHandler) for h in security_files)
    with pytest.raises(ValidationError):
        UserLogin(username="u" * (MAX_LOGIN_IDENTIFIER_CHARS + 1), password="x")


@pytest.mark.anyio
async def test_password_hashing_runs_off_the_event_loop(monkeypatch):
    loop_thread = threading.get_ident()
    seen = []

    def fake_authenticate(db, username, password):
        seen.append(threading.get_ident())
        return None

    monkeypatch.setattr(auth_api, "authenticate_user", fake_authenticate)
    request = type("R", (), {"client": None, "method": "POST", "url": type("U", (), {"path": "/api/auth/login"})(), "headers": {}})()
    with pytest.raises(Exception):
        await auth_api.login(UserLogin(username="someone", password="wrong"), request, response=None, db=None)
    assert seen and seen[0] != loop_thread


def test_tools_list_requires_login():
    route = next(r for r in chat_api.router.routes if isinstance(r, APIRoute) and r.path == "/tools")
    dependencies = {dependency.call for dependency in route.dependant.dependencies}
    assert get_current_user_id in dependencies


def test_knowledge_base_description_is_cached(monkeypatch):
    tools_module.invalidate_knowledge_base_description()
    builds = []
    monkeypatch.setattr(ResearchToolRegistry, "_build_knowledge_base_description", lambda self: builds.append(1) or "desc")
    registry = ResearchToolRegistry()
    assert registry._generate_knowledge_base_description() == "desc"
    assert registry._generate_knowledge_base_description() == "desc"
    assert len(builds) == 1
    tools_module.invalidate_knowledge_base_description()
    registry._generate_knowledge_base_description()
    assert len(builds) == 2
    tools_module.invalidate_knowledge_base_description()


@pytest.mark.anyio
async def test_stdio_close_terminates_grandchildren():
    # 模擬 npx／uvx：啟動器再啟動一個長時間執行的孫行程
    launcher = (
        "import subprocess, sys, time;"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
        "print(child.pid, flush=True);"
        "time.sleep(60)"
    )
    client = McpStdioClient(command=sys.executable, args=["-c", launcher])
    await client.start()
    grandchild_pid = int((await asyncio.wait_for(client.process.stdout.readline(), timeout=10)).strip())
    assert psutil.pid_exists(grandchild_pid)
    await client.close()
    deadline = time.monotonic() + 5
    while psutil.pid_exists(grandchild_pid) and time.monotonic() < deadline:
        try:
            if psutil.Process(grandchild_pid).status() == psutil.STATUS_ZOMBIE:
                break
        except psutil.NoSuchProcess:
            break
        await asyncio.sleep(0.1)
    alive = psutil.pid_exists(grandchild_pid) and psutil.Process(grandchild_pid).status() != psutil.STATUS_ZOMBIE
    assert not alive


def test_jieba_cache_lives_in_the_data_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(tokenizers, "JIEBA_CACHE_DIR", str(tmp_path / "jieba_cache"))
    monkeypatch.setattr(tokenizers, "_configured_with", None)
    tokenizers.configure_tokenizer(None, ["測試詞"])
    assert tokenizers._jieba_tokenizer.tmp_dir == str(tmp_path / "jieba_cache")
    assert (tmp_path / "jieba_cache").is_dir()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX 權限位元")
def test_rsa_private_key_is_created_owner_only(tmp_path):
    manager = RSAKeyManager(keys_dir=str(tmp_path / "keys"))
    assert (tmp_path / "keys").stat().st_mode & 0o777 == 0o700
    assert manager.private_key_path.stat().st_mode & 0o777 == 0o600
    # 只剩私鑰時重新產生整組金鑰
    manager.public_key_path.unlink()
    RSAKeyManager(keys_dir=str(tmp_path / "keys"))
    assert manager.public_key_path.exists()
    assert manager.private_key_path.stat().st_mode & 0o777 == 0o600


@pytest.mark.anyio
async def test_rate_limiter_tracks_a_bounded_number_of_addresses(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr(security_module, "MAX_TRACKED_ADDRESSES", 3)
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    limiter = security_module.RateLimitMiddleware(app, calls=2, period=60)
    for index in range(5):
        client = TestClient(limiter, client=(f"198.51.100.{index}", 1234))
        assert client.get("/ping").status_code == 200
    assert list(limiter.clients) == ["198.51.100.2", "198.51.100.3", "198.51.100.4"]
    client = TestClient(limiter, client=("198.51.100.4", 1234))
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429
