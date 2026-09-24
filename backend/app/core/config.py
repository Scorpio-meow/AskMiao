import os
import re
from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BACKEND_DIR / ".env"
# 相對路徑一律以 backend/ 為基準，避免從其他目錄啟動時指到錯誤位置
PATH_SETTING_KEYS = (
    "UPLOAD_DIR",
    "DATA_DIR",
    "FAISS_INDEX_PATH",
    "BM25_INDEX_DIR",
    "METADATA_PATH",
    "HF_HOME",
    "HF_HUB_CACHE",
    "SENTENCE_TRANSFORMERS_HOME",
    "DOMAIN_PROFILE_PATH",
    "JIEBA_DICTIONARY",
)
DOMAIN_NAME_PATTERN = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)*")
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
        validate_default=True
    )
    LLM_API_BASE: str = "http://localhost:5000"
    LLM_TIMEOUT: float = 120.0
    MODEL_NAME: Optional[str] = None
    OLLAMA_API_KEY: Optional[str] = None
    OLLAMA_TEMPERATURE: Optional[float] = None
    OLLAMA_NUM_PREDICT: Optional[int] = None
    ENABLE_WEB_SEARCH: bool
    # web_fetch 可讀取的網域（含子網域），逗號分隔；明確寫 * 才表示不限制
    WEB_FETCH_ALLOWED_DOMAINS: str
    # 同一次提問中知識庫工具回傳過內容後，是否拒絕 web_search 與 web_fetch
    BLOCK_WEB_TOOLS_AFTER_KB: bool
    AGENT_MAX_TURNS: int = Field(ge=1)
    CONVERSATION_HISTORY_MESSAGES: int = Field(ge=0)
    AZURE_OPENAI_API_KEY: Optional[str] = None
    AZURE_OPENAI_ENDPOINT: Optional[str] = None
    AZURE_OPENAI_DEPLOYMENT: Optional[str] = None
    AVAILABLE_MODELS: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_API_BASE: str = "https://api.openai.com/v1"
    OPENAI_VISION_MODEL: str = "gpt-4o"
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_API_BASE: str = "https://api.anthropic.com"
    ANTHROPIC_MAX_TOKENS: Optional[int] = Field(default=None, ge=1)
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_API_BASE: str = "https://generativelanguage.googleapis.com"
    GEMINI_VISION_MODEL: str = "gemini-2.5-flash"
    OLLAMA_SEARCH_ENDPOINT: str = "https://ollama.com/api/web_search"
    OLLAMA_FETCH_ENDPOINT: str = "https://ollama.com/api/web_fetch"
    DUCKDUCKGO_SEARCH_ENDPOINT: str = "https://html.duckduckgo.com/html/"
    DEFAULT_CONVERSATION_TITLE: str = "新對話"
    COOKIE_SECURE: Optional[bool] = None
    COOKIE_SAMESITE: str = "lax"
    EXTERNAL_TAGS_URL: str = ""
    LLM_TAGS_TIMEOUT: float = 10.0
    ADD_NGROK_HEADER: bool = False
    ADMIN_API_KEY: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "RS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ENVIRONMENT: str = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    RELOAD: bool = True
    LOG_LEVEL: str = "INFO"
    DATABASE_URL: str
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_RECYCLE: int = 3600
    DB_POOL_PRE_PING: bool = True
    SQLALCHEMY_ECHO: bool = False
    EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"
    RERANKER_MODEL: str = "BAAI/bge-reranker-base"
    HF_HOME: Optional[str] = None
    HF_HUB_CACHE: Optional[str] = None
    SENTENCE_TRANSFORMERS_HOME: Optional[str] = None
    HF_HUB_OFFLINE: Optional[bool] = None
    HF_HUB_DISABLE_SYMLINKS_WARNING: Optional[bool] = None
    FORCE_CPU: bool = True
    USE_FP16_QUANTIZATION: bool = False
    GPU_BATCH_SIZE: int = 128
    CPU_BATCH_SIZE: int = 64
    USE_FAISS_GPU: bool = False
    FAISS_GPU_DEVICE: int = 0
    FAISS_GPU_TEMP_MEMORY: int = 2147483648
    SIMILARITY_THRESHOLD: float = 0.30
    TOP_K: int = 30
    RRF_K: int = Field(ge=1)
    RERANK_TOP_K: int = 50
    FINAL_K: int = 8
    RERANK_WEIGHT: float = 0.85
    # 重排模型機率低於此值的片段視為無關（精確比對到網址、貼文 ID、日期者除外）
    RERANK_RELEVANCE_THRESHOLD: float = Field(ge=0.0, le=1.0)
    # 領域詞、結構化記錄日期欄位與摘要備援規則（JSON）
    DOMAIN_PROFILE_PATH: str
    # 選填：替換 jieba 主詞典（例如繁體較友善的 dict.txt.big），未設定時使用 jieba 內建詞典
    JIEBA_DICTIONARY: Optional[str] = None
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 150
    MAX_FILE_SIZE_MB: int = 50
    UPLOAD_DIR: str = "data/uploads"
    DATA_DIR: str = "data"
    FAISS_INDEX_PATH: str = "data/faiss_index.bin"
    BM25_INDEX_DIR: str = "data/bm25_index"
    METADATA_PATH: str = "data/index_metadata.pkl"
    ALLOWED_ORIGINS: str = "http://localhost:3001,https://localhost:3001,http://127.0.0.1:3001,https://127.0.0.1:3001"
    DEVTUNNEL_URL: str = ""
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    UPLOADS_WATCHER_INTERVAL: int = 30
    ENABLE_BATCH_ACCUMULATION: bool = False
    BATCH_ACCUMULATOR_SIZE: int = 32
    BASE_URL: str = "http://backend:8001"
    @field_validator(*PATH_SETTING_KEYS)
    @classmethod
    def _resolve_backend_relative_path(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        path = Path(value).expanduser()
        return str(path if path.is_absolute() else (BACKEND_DIR / path).resolve())
    @field_validator("WEB_FETCH_ALLOWED_DOMAINS")
    @classmethod
    def _validate_web_fetch_domains(cls, value: str) -> str:
        domains = [d.strip().lower() for d in value.split(",") if d.strip()]
        if not domains:
            raise ValueError("WEB_FETCH_ALLOWED_DOMAINS 不可為空；不限制網域請明確設定為 *")
        if "*" in domains and len(domains) > 1:
            raise ValueError("WEB_FETCH_ALLOWED_DOMAINS 設為 * 時不可再列其他網域")
        invalid = [d for d in domains if d != "*" and not DOMAIN_NAME_PATTERN.fullmatch(d)]
        if invalid:
            raise ValueError(f"WEB_FETCH_ALLOWED_DOMAINS 含無效網域（只填網域，不含通訊協定與路徑）：{', '.join(invalid)}")
        return ",".join(domains)
    @property
    def web_fetch_allowed_domains(self) -> List[str]:
        return self.WEB_FETCH_ALLOWED_DOMAINS.split(",")
    @property
    def allowed_origins_list(self) -> List[str]:
        if not self.ALLOWED_ORIGINS:
            return []
        origins = [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]
        if self.DEVTUNNEL_URL and self.DEVTUNNEL_URL.strip():
            origins.append(self.DEVTUNNEL_URL.strip())
        return origins
HF_ENVIRONMENT_KEYS = (
    "HF_HOME",
    "HF_HUB_CACHE",
    "SENTENCE_TRANSFORMERS_HOME",
    "HF_HUB_OFFLINE",
    "HF_HUB_DISABLE_SYMLINKS_WARNING",
)
def export_hf_environment(config: Settings) -> None:
    """Hugging Face 相關套件只讀環境變數，且在匯入時就決定快取位置與離線模式，須在載入模型前寫入 os.environ"""
    for key in HF_ENVIRONMENT_KEYS:
        value = getattr(config, key)
        if value is None:
            continue
        os.environ[key] = ("1" if value else "0") if isinstance(value, bool) else value
settings = Settings()
export_hf_environment(settings)
