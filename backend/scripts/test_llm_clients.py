import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.core.config import settings
from app.core.llm_client import get_available_models, call_llm
class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code
        
    def json(self):
        return self._json_data
        
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP Error {self.status_code}")
async def run_tests():
    print("=== 開始測試多 LLM 客戶端路由與格式 ===")
    
    print("\n[測試 1] 驗證 get_available_models() 動態清單：")
    with patch.dict(os.environ, {"AVAILABLE_MODELS": ""}):
        with patch.object(settings, "AZURE_OPENAI_API_KEY", "azure-key"), \
             patch.object(settings, "AZURE_OPENAI_ENDPOINT", "https://azure.com"), \
             patch.object(settings, "AZURE_OPENAI_DEPLOYMENT", "azure-gpt"), \
             patch.object(settings, "OPENAI_API_KEY", "openai-key"), \
             patch.object(settings, "ANTHROPIC_API_KEY", "anthropic-key"), \
             patch.object(settings, "GEMINI_API_KEY", "gemini-key"):
            
            models = get_available_models()
            print(f"啟動所有 Key 時的模型列表: {models}")
            assert "azure-gpt" in models
            assert "gpt-6-sol" in models
            assert "claude-opus-5-5" in models
            assert "gemini-3.5-flash" in models
            print("=> 測試 1 成功！")
    print("\n[測試 2] 驗證 OpenAI 路由與調用格式：")
    mock_post = AsyncMock()
    mock_post.return_value = MockResponse({
        "choices": [{
            "message": {
                "content": "Hello from OpenAI"
            }
        }]
    })
    
    with patch("httpx.AsyncClient.post", mock_post):
        with patch.object(settings, "OPENAI_API_KEY", "openai-test-key"):
            messages = [{"role": "user", "content": "你好"}]
            response = await call_llm(messages, model_name="gpt-6-sol")
            print(f"LLM 回傳: {response}")
            assert response == "Hello from OpenAI"
            
            args, kwargs = mock_post.call_args
            url = args[0]
            json_payload = kwargs.get("json")
            headers = kwargs.get("headers")
            
            print(f"請求 URL: {url}")
            print(f"請求 Payload: {json_payload}")
            print(f"請求 Headers: {headers}")
            
            assert url == "https://api.openai.com/v1/chat/completions"
            assert headers["Authorization"] == "Bearer openai-test-key"
            assert json_payload["model"] == "gpt-6-sol"
            assert json_payload["messages"] == messages
            print("=> 測試 2 成功！")
    print("\n[測試 3] 驗證 Google Gemini 路由與調用格式：")
    mock_post = AsyncMock()
    mock_post.return_value = MockResponse({
        "choices": [{
            "message": {
                "content": "Hello from Gemini"
            }
        }]
    })
    
    with patch("httpx.AsyncClient.post", mock_post):
        with patch.object(settings, "GEMINI_API_KEY", "gemini-test-key"):
            messages = [{"role": "user", "content": "你好"}]
            response = await call_llm(messages, model_name="gemini-3.5-flash")
            print(f"LLM 回傳: {response}")
            assert response == "Hello from Gemini"
            
            args, kwargs = mock_post.call_args
            url = args[0]
            json_payload = kwargs.get("json")
            headers = kwargs.get("headers")
            
            print(f"請求 URL: {url}")
            print(f"請求 Payload: {json_payload}")
            print(f"請求 Headers: {headers}")
            
            assert url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            assert headers["Authorization"] == "Bearer gemini-test-key"
            assert json_payload["model"] == "gemini-3.5-flash"
            assert json_payload["messages"] == messages
            print("=> 測試 3 成功！")
    print("\n[測試 4] 驗證 Anthropic Claude 路由與調用格式（官方 anthropic SDK）：")
    mock_create = AsyncMock(return_value=MagicMock(
        stop_reason="end_turn",
        content=[MagicMock(type="text", text="Hello from Claude")]
    ))
    fake_client = MagicMock()
    fake_client.with_options.return_value.messages.create = mock_create

    with patch("app.core.llm_client._anthropic_client_instance", return_value=fake_client):
        with patch.object(settings, "ANTHROPIC_API_KEY", "claude-test-key"), \
             patch.object(settings, "ANTHROPIC_MAX_TOKENS", 16000):
            messages = [
                {"role": "system", "content": "你是繁體中文助手"},
                {"role": "user", "content": "你好"}
            ]
            response = await call_llm(messages, model_name="claude-opus-5-5")
            print(f"LLM 回傳: {response}")
            assert response == "Hello from Claude"

            kwargs = mock_create.call_args.kwargs
            print(f"SDK 呼叫參數: {kwargs}")

            assert kwargs["model"] == "claude-opus-5-5"
            assert kwargs["max_tokens"] == 16000
            assert kwargs["system"] == "你是繁體中文助手"
            assert kwargs["messages"] == [{"role": "user", "content": "你好"}]
            print("=> 測試 4 成功！")
    print("\n=== 所有測試皆通過！ ===")
if __name__ == "__main__":
    asyncio.run(run_tests())
