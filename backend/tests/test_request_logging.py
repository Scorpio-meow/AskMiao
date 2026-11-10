import asyncio
import io
import json
import logging
from types import SimpleNamespace
import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.core import llm_client
from app.core.access_log import AccessLogMiddleware
from app.core.config import Settings, settings
from app.core.error_response import build_error_payload
from app.core.llm_client import LlmEndpoint
from app.core.request_context import REQUEST_ID_HEADER, begin_request, bind_request_user, current_request_id, end_request
from app.core.security import RateLimitMiddleware, SecurityHeadersMiddleware
from app.core import security_logging
from app.core.security_logging import configure_log_handler, log_fields, log_formatter, log_security_event, rotating_log_file_handler
from app.rag.tools import ResearchToolRegistry
from test_llm_providers import completion_stream
LOCAL_OLLAMA = LlmEndpoint("ollama", "http://localhost:11434", None, None, False)
OPENAI = LlmEndpoint("openai", "https://api.openai.com/v1", "sk-test-secret", None, False)
SECRET_PROMPT = "請保密的提問內容"
@pytest.fixture
def formatted_logs():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(log_formatter())
    loggers = [logging.getLogger(name) for name in ("app.access", "tests.request_logging", "app.core.llm_client", "app.rag.tools", "app.core.security")]
    levels = [lg.level for lg in loggers]
    for lg in loggers:
        lg.addHandler(handler)
        lg.setLevel(logging.INFO)
    yield stream
    for lg, level in zip(loggers, levels):
        lg.removeHandler(handler)
        lg.setLevel(level)
def _access_app() -> FastAPI:
    app = FastAPI()
    request_logger = logging.getLogger("tests.request_logging")
    def current_user() -> int:
        bind_request_user(7)
        return 7
    @app.get("/api/items")
    def list_items(user_id: int = Depends(current_user)):
        request_logger.info("handler ran")
        return {"user_id": user_id, "request_id": current_request_id()}
    @app.get("/api/boom")
    async def boom():
        raise RuntimeError("boom")
    @app.get("/health")
    async def health():
        return {"status": "healthy"}
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AccessLogMiddleware)
    return app
def _access_lines(stream: io.StringIO):
    return [line for line in stream.getvalue().splitlines() if " - app.access - " in line]
def test_access_log_records_request_and_shares_request_id_with_handler_logs(formatted_logs):
    client = TestClient(_access_app(), client=("203.0.113.9", 4321))
    response = client.get(
        "/api/items?code=oauth-secret-code&state=s3cret&limit=5",
        headers={"Authorization": "Bearer jwt-secret-token", "Cookie": "refresh_token=cookie-secret"},
    )
    assert response.status_code == 200
    request_id = response.headers[REQUEST_ID_HEADER]
    assert response.json() == {"user_id": 7, "request_id": request_id}
    output = formatted_logs.getvalue()
    handler_line = next(line for line in output.splitlines() if "handler ran" in line)
    assert f"[{request_id}]" in handler_line
    [access_line] = _access_lines(formatted_logs)
    assert f"[{request_id}]" in access_line
    for expected in ("method=GET", "path=/api/items", "query_keys=code,state,limit", "status=200", "ip=203.0.113.9", "user=7", "duration_ms=", "bytes="):
        assert expected in access_line
    for secret in ("oauth-secret-code", "s3cret", "jwt-secret-token", "cookie-secret"):
        assert secret not in output
def test_trusted_request_id_is_reused_and_malformed_ones_are_replaced(formatted_logs):
    client = TestClient(_access_app())
    reused = client.get("/api/items", headers={REQUEST_ID_HEADER: "proxy-req-0001"})
    assert reused.headers[REQUEST_ID_HEADER] == "proxy-req-0001"
    for malformed in ("short", "has space in it", "x" * 65, "bad‮id-00000"):
        response = client.get("/api/items", headers={REQUEST_ID_HEADER: malformed.encode("utf-8")})
        assert response.headers[REQUEST_ID_HEADER] != malformed
        assert len(response.headers[REQUEST_ID_HEADER]) == 16
def test_unhandled_error_is_logged_as_server_error_and_non_api_paths_are_skipped(formatted_logs):
    client = TestClient(_access_app(), raise_server_exceptions=False)
    assert client.get("/api/boom").status_code == 500
    assert client.get("/health").status_code == 200
    [access_line] = _access_lines(formatted_logs)
    assert " - WARNING - " in access_line
    assert "status=500" in access_line and "error=RuntimeError" in access_line
    assert "user=-" in access_line
def test_error_payload_and_security_events_carry_the_request_id(isolated_log_dir):
    token = begin_request("req-for-error-001")
    try:
        payload = build_error_payload(logging.getLogger("tests.request_logging"), "失敗", RuntimeError("x"))
        log_security_event("REQUEST_ID_CHECK", details={"marker": "request-id-check"})
    finally:
        end_request(token)
    assert payload["request_id"] == "req-for-error-001"
    assert current_request_id() == "-"
    security_line = next(
        line for line in (isolated_log_dir / "security.log").read_text(encoding="utf-8").splitlines() if "request-id-check" in line
    )
    assert "[req-for-error-001]" in security_line
    assert json.loads(security_line.split("] ", 1)[1])["request_id"] == "req-for-error-001"
def test_an_unused_handler_on_the_same_file_does_not_block_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(security_logging, "LOG_FILE_MAX_BYTES", 200)
    attached = rotating_log_file_handler("app.log")
    stray = rotating_log_file_handler("app.log")
    errors = []
    monkeypatch.setattr(attached, "handleError", lambda record: errors.append(record))
    rotation_logger = logging.getLogger("tests.request_logging.rotation")
    monkeypatch.setattr(rotation_logger, "propagate", False)
    rotation_logger.addHandler(attached)
    try:
        for index in range(20):
            rotation_logger.warning("x" * 40 + str(index))
    finally:
        rotation_logger.removeHandler(attached)
        attached.close()
        stray.close()
    assert errors == []
    assert {"app.log", "app.log.1", "app.log.2"} <= {path.name for path in tmp_path.iterdir()}
def test_log_handlers_follow_log_level_and_fields_are_quoted(monkeypatch):
    monkeypatch.setattr(settings, "LOG_LEVEL", "WARNING")
    handler = configure_log_handler(logging.StreamHandler(io.StringIO()))
    assert handler.level == logging.WARNING
    assert log_fields(a=1, b=None, c="x y", d="k=v", e="") == 'a=1 c="x y" d="k=v" e=""'
    assert Settings(LOG_LEVEL=" debug ").LOG_LEVEL == "DEBUG"
    with pytest.raises(ValidationError):
        Settings(LOG_LEVEL="verbose")
def _llm_lines(stream: io.StringIO):
    return [line for line in stream.getvalue().splitlines() if " - app.core.llm_client - " in line]
@pytest.mark.asyncio
async def test_ollama_chat_logs_duration_usage_and_phase_timings(monkeypatch, formatted_logs):
    def handler(request):
        return httpx.Response(200, json={
            "message": {"role": "assistant", "content": "答案"},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 321,
            "eval_count": 12,
            "load_duration": 2_000_000,
            "prompt_eval_duration": 150_000_000,
            "eval_duration": 90_000_000,
            "total_duration": 250_000_000,
        })
    monkeypatch.setattr(llm_client, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    message = await llm_client.chat_completion(
        [{"role": "user", "content": SECRET_PROMPT}], endpoint=LOCAL_OLLAMA, model_name="qwen3:8b", timeout=42
    )
    assert message == {"role": "assistant", "content": "答案"}
    start, done = _llm_lines(formatted_logs)
    assert "LLM 呼叫開始" in start and "timeout_s=42" in start and f"prompt_chars={len(SECRET_PROMPT)}" in start
    assert "host=localhost" in start
    for expected in ("LLM 呼叫完成", "mode=chat", "status=ok", "input_tokens=321", "output_tokens=12", "load_ms=2",
                     "prompt_eval_ms=150", "eval_ms=90", "total_ms=250", "stop_reason=stop", "duration_ms=", "output_chars=2"):
        assert expected in done
    assert SECRET_PROMPT not in formatted_logs.getvalue()
@pytest.mark.asyncio
async def test_llm_timeout_logs_which_phase_failed_and_the_timeout(monkeypatch, formatted_logs):
    def handler(request):
        raise httpx.ReadTimeout("", request=request)
    monkeypatch.setattr(llm_client, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(httpx.ReadTimeout):
        await llm_client.chat_completion([{"role": "user", "content": "hi"}], endpoint=LOCAL_OLLAMA, model_name="qwen3:8b", timeout=300)
    failed = _llm_lines(formatted_logs)[-1]
    assert " - WARNING - " in failed
    for expected in ("LLM 呼叫失敗", "status=error", "error=ReadTimeout", "timeout_s=300", "duration_ms="):
        assert expected in failed
@pytest.mark.asyncio
async def test_openai_chat_logs_usage_without_secrets(monkeypatch, formatted_logs):
    def handler(request):
        return completion_stream({"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "search_knowledge_base", "arguments": "{}"}}
        ]}, "tool_calls", {"prompt_tokens": 50, "completion_tokens": 7, "prompt_tokens_details": {"cached_tokens": 32},
                          "completion_tokens_details": {"reasoning_tokens": 4}})
    monkeypatch.setattr(llm_client, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await llm_client.chat_completion([{"role": "user", "content": "hi"}], endpoint=OPENAI, model_name="gpt-5.4")
    done = _llm_lines(formatted_logs)[-1]
    for expected in ("input_tokens=50", "output_tokens=7", "cached_tokens=32", "reasoning_tokens=4", "tool_calls=1", "stop_reason=tool_calls"):
        assert expected in done
    assert "sk-test-secret" not in formatted_logs.getvalue()
@pytest.mark.asyncio
async def test_ollama_stream_logs_first_chunk_and_final_usage(monkeypatch, formatted_logs):
    def handler(request):
        return httpx.Response(200, content=(
            b'{"message":{"content":"ab"},"done":false}\n'
            b'{"message":{"content":"cd"},"done":false}\n'
            b'{"message":{"content":""},"done":true,"done_reason":"length","prompt_eval_count":9,"eval_count":2,"eval_duration":5000000}\n'
        ))
    monkeypatch.setattr(llm_client, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    chunks = [chunk async for chunk in llm_client.stream_completion(
        [{"role": "user", "content": "hi"}], endpoint=LOCAL_OLLAMA, model_name="qwen3:8b"
    )]
    assert chunks == ["ab", "cd"]
    start, done = _llm_lines(formatted_logs)
    assert f"timeout_s={settings.LLM_TIMEOUT}" in start
    for expected in ("LLM 呼叫完成", "mode=stream", "chunks=2", "output_chars=4", "first_chunk_ms=", "input_tokens=9",
                     "output_tokens=2", "eval_ms=5", "stop_reason=length"):
        assert expected in done
@pytest.mark.asyncio
async def test_stream_stopped_by_the_consumer_is_logged_as_cancelled(monkeypatch, formatted_logs):
    def handler(request):
        return httpx.Response(200, content=b'{"message":{"content":"ab"}}\n{"message":{"content":"cd"}}\n')
    monkeypatch.setattr(llm_client, "_http_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    stream = llm_client.stream_completion([{"role": "user", "content": "hi"}], endpoint=LOCAL_OLLAMA, model_name="qwen3:8b")
    assert await stream.__anext__() == "ab"
    await stream.aclose()
    stopped = _llm_lines(formatted_logs)[-1]
    assert "LLM 呼叫中止" in stopped and "status=cancelled" in stopped and "chunks=1" in stopped
def test_anthropic_and_responses_usage_are_normalized():
    usage = SimpleNamespace(input_tokens=10, output_tokens=3, cache_read_input_tokens=8, cache_creation_input_tokens=None)
    response = SimpleNamespace(usage=usage, stop_reason="end_turn", model="claude-sonnet-5-5")
    assert llm_client._anthropic_stats(response, "claude-opus-5-5") == {
        "input_tokens": 10, "output_tokens": 3, "cache_read_tokens": 8, "stop_reason": "end_turn", "served_model": "claude-sonnet-5-5",
    }
    assert llm_client._anthropic_stats(SimpleNamespace(stop_reason=None, content=[]), "m") == {}
    assert llm_client._responses_stats({"status": "completed", "usage": {
        "input_tokens": 5, "output_tokens": 6, "input_tokens_details": {"cached_tokens": 1}, "output_tokens_details": {"reasoning_tokens": 2},
    }}) == {"input_tokens": 5, "output_tokens": 6, "cached_tokens": 1, "reasoning_tokens": 2, "stop_reason": "completed"}
def _tool_lines(stream: io.StringIO):
    return [line for line in stream.getvalue().splitlines() if " - app.rag.tools - " in line and "工具呼叫" in line]
@pytest.mark.asyncio
async def test_tool_calls_log_name_duration_and_status_without_argument_values(monkeypatch, formatted_logs):
    registry = ResearchToolRegistry()
    assert "error" in await registry.execute_tool("search_knowledge_base", {"query": SECRET_PROMPT, "top_k": 2})
    async def succeed(name, arguments, user_id, conversation_id):
        return {"ok": True}
    async def explode(name, arguments, user_id, conversation_id):
        raise ValueError("bad top_k")
    monkeypatch.setattr(registry, "_dispatch_tool", succeed)
    assert await registry.execute_tool("mcp_weather_now", {"city": "台北"}) == {"ok": True}
    monkeypatch.setattr(registry, "_dispatch_tool", explode)
    with pytest.raises(ValueError):
        await registry.execute_tool("exchange_rate", {})
    errored, succeeded, raised = _tool_lines(formatted_logs)
    assert " - WARNING - " in errored
    for expected in ("tool=search_knowledge_base", "kind=builtin", "status=error", "arg_keys=query,top_k", "duration_ms=", "result_chars=", "error="):
        assert expected in errored
    for expected in ("tool=mcp_weather_now", "kind=mcp", "status=ok", "arg_keys=city"):
        assert expected in succeeded
    for expected in ("工具呼叫失敗", "tool=exchange_rate", "kind=api", "status=exception", "error=ValueError"):
        assert expected in raised
    assert SECRET_PROMPT not in "\n".join(_tool_lines(formatted_logs)) and "台北" not in formatted_logs.getvalue()
@pytest.mark.anyio
@pytest.mark.parametrize("user_id, decision, status", [(5, False, "not_approved"), (None, None, "approval_unavailable")])
async def test_tool_calls_that_never_run_are_logged_with_the_reason(monkeypatch, caplog, user_id, decision, status):
    from test_tool_approval import approval_agent, run_with_decision
    agent, executed = approval_agent(monkeypatch)
    with caplog.at_level(logging.INFO, logger="app.rag.agent"):
        await run_with_decision(agent, decision, user_id=user_id)
    assert executed == []
    messages = [record.getMessage() for record in caplog.records if record.name == "app.rag.agent"]
    step = next(message for message in messages if "呼叫工具" in message)
    assert "tool=create_order" in step and "arg_keys=item,qty" in step and "'item'" not in step
    skipped = next(message for message in messages if "工具呼叫未執行" in message)
    assert "tool=create_order" in skipped and f"status={status}" in skipped and "duration_ms=" in skipped
def test_retrieval_log_records_query_length_only(monkeypatch, caplog):
    from test_hybrid_retrieval import FakeCrossEncoder, chunk, make_retriever
    documents = [chunk(1, "特休依年資計算"), chunk(2, "病假需附證明")]
    retriever = make_retriever(monkeypatch, documents, documents, documents, FakeCrossEncoder({}, default_relevance=0.9))
    with caplog.at_level(logging.INFO, logger="app.rag.retrievers.hybrid"):
        retriever.rank(SECRET_PROMPT)
    [line] = [record.getMessage() for record in caplog.records if record.getMessage().startswith("Retrieval ")]
    assert f"query_chars={len(SECRET_PROMPT)}" in line and "reranked=2" in line
    assert SECRET_PROMPT not in line
def _rate_limited_app(period: float) -> RateLimitMiddleware:
    app = FastAPI()
    @app.get("/{name}")
    async def ping(name: str):
        return {"ok": True}
    return RateLimitMiddleware(app, calls=1, period=period)
def _rate_lines(stream: io.StringIO):
    return [line for line in stream.getvalue().splitlines() if " - app.core.security - " in line]
@pytest.mark.asyncio
async def test_rate_limit_warns_once_per_window_and_summarizes_blocked_requests(formatted_logs):
    limiter = _rate_limited_app(period=0.3)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=limiter, client=("198.51.100.7", 1)), base_url="http://test") as client:
        statuses = [(await client.get(path)).status_code for path in ("/a", "/a", "/a", "/b")]
        assert statuses == [200, 429, 429, 429]
        assert len(_rate_lines(formatted_logs)) == 1
        await asyncio.sleep(0.5)
    started, summary = _rate_lines(formatted_logs)
    assert "速率限制開始擋下請求" in started and "ip=198.51.100.7" in started and "path=/a" in started and "limit=1" in started
    assert "速率限制視窗結束" in summary and "blocked=3" in summary and "/a×2" in summary and "/b×1" in summary
    assert limiter.blocked_windows == {}
@pytest.mark.asyncio
async def test_stale_rate_limit_window_is_closed_before_a_new_one_starts(formatted_logs):
    limiter = _rate_limited_app(period=60)
    limiter._record_block("198.51.100.8", "/a", 0.0)
    first_window = limiter.blocked_windows["198.51.100.8"]
    limiter._record_block("198.51.100.8", "/a", 10.0)
    limiter._record_block("198.51.100.8", "/b", 61.0)
    current_window = limiter.blocked_windows["198.51.100.8"]
    started, summary, restarted = _rate_lines(formatted_logs)
    assert "blocked=2" in summary and "path=/b" in restarted
    limiter._expire_blocked_window("198.51.100.8", first_window)
    assert limiter.blocked_windows["198.51.100.8"] is current_window
    assert current_window.blocked == 1