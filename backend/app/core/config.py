import os
import re
from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BACKEND_DIR / ".env"
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
    "SKILLS_DIR",
    "LOG_DIR",
)
DOMAIN_NAME_PATTERN = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)*")
LOG_LEVEL_NAMES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
        validate_default=True
    )
    LLM_TIMEOUT: float = 120.0
    OLLAMA_API_KEY: Optional[str] = None
    OLLAMA_TEMPERATURE: Optional[float] = None
    OLLAMA_NUM_PREDICT: Optional[int] = None
    OLLAMA_NUM_CTX: Optional[int] = Field(default=None, ge=1)
    ENABLE_WEB_SEARCH: bool
    WEB_FETCH_ALLOWED_DOMAINS: str
    BLOCK_WEB_TOOLS_AFTER_KB: bool
    CONVERSATION_HISTORY_MESSAGES: int = Field(ge=0)
    OLLAMA_SEARCH_ENDPOINT: str = "https://ollama.com/api/web_search"
    OLLAMA_FETCH_ENDPOINT: str = "https://ollama.com/api/web_fetch"
    DUCKDUCKGO_SEARCH_ENDPOINT: str = "https://html.duckduckgo.com/html/"
    DEFAULT_CONVERSATION_TITLE: str = "新對話"
    COOKIE_SECURE: bool
    COOKIE_SAMESITE: str = "lax"
    LLM_TAGS_TIMEOUT: float = 10.0
    ALLOW_REGISTRATION: bool
    TOOL_SECRETS_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    LOGIN_MAX_FAILURES_PER_ACCOUNT: int = Field(ge=1)
    LOGIN_MAX_FAILURES_PER_ADDRESS: int = Field(ge=1)
    LOGIN_FAILURE_WINDOW_SECONDS: int = Field(ge=1)
    LOGIN_LOCKOUT_SECONDS: int = Field(ge=1)
    ENVIRONMENT: str = "development"
    HOST: str
    PORT: int = 8001
    RELOAD: bool
    ENABLE_API_DOCS: bool
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str
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
    RERANKER_OPENVINO_DEVICE: Optional[str] = None
    RERANKER_OPENVINO_MAX_LENGTH: Optional[int] = Field(default=None, ge=1)
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
    RERANK_RELEVANCE_THRESHOLD: float = Field(ge=0.0, le=1.0)
    DOMAIN_PROFILE_PATH: str
    JIEBA_DICTIONARY: Optional[str] = None
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 150
    MAX_FILE_SIZE_MB: int = 50
    UPLOAD_DIR: str = "data/uploads"
    SKILLS_DIR: str
    DATA_DIR: str = "data"
    FAISS_INDEX_PATH: str = "data/faiss_index.bin"
    BM25_INDEX_DIR: str = "data/bm25_index"
    METADATA_PATH: str = "data/index_metadata.json"
    ALLOWED_ORIGINS: str = "http://localhost:3001,https://localhost:3001,http://127.0.0.1:3001,https://127.0.0.1:3001"
    DEVTUNNEL_URL: str = ""
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    FORWARDED_ALLOW_IPS: Optional[str] = None
    UPLOADS_WATCHER_INTERVAL: int = 30
    @field_validator(*PATH_SETTING_KEYS)
    @classmethod
    def _resolve_backend_relative_path(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        path = Path(value).expanduser()
        return str(path if path.is_absolute() else (BACKEND_DIR / path).resolve())
    @field_validator("LOG_LEVEL")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in LOG_LEVEL_NAMES:
            raise ValueError(f"LOG_LEVEL 必須是 {', '.join(LOG_LEVEL_NAMES)} 其中之一")
        return level
    @field_validator("TOOL_SECRETS_KEY")
    @classmethod
    def _validate_tool_secrets_key(cls, value: str) -> str:
        from cryptography.fernet import Fernet
        try:
            Fernet(value.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as e:
            raise ValueError(
                "TOOL_SECRETS_KEY 必須是 Fernet 金鑰，可用 "
                "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" 產生"
            ) from e
        return value
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
    for key in HF_ENVIRONMENT_KEYS:
        value = getattr(config, key)
        if value is None:
            continue
        os.environ[key] = ("1" if value else "0") if isinstance(value, bool) else value
settings = Settings()
export_hf_environment(settings)