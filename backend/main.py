import os
import logging
from logging.handlers import RotatingFileHandler
import torch
import uvicorn
from fastapi import FastAPI
from app import __version__
from app.core.config import settings
from app.core.limits import LOG_FILE_BACKUP_COUNT, LOG_FILE_MAX_BYTES
from app.core.lifespan import lifespan
from app.middleware import setup_middlewares
from app.api import chat, admin, documents, tags as tags_router, auth, api_tools, mcp
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)
log_level = settings.LOG_LEVEL.upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            os.path.join(LOGS_DIR, 'app.log'),
            maxBytes=LOG_FILE_MAX_BYTES,
            backupCount=LOG_FILE_BACKUP_COUNT,
            encoding='utf-8'
        )
    ]
)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
# httpx／httpcore 的 INFO 日誌會記下完整請求網址，查詢字串型 API 金鑰等憑證會因此明文落地
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
app = FastAPI(
    title="AskMiao API",
    description="AskMiao 智慧知識庫對話系統：Agentic RAG 自主研究、混合檢索與外部工具整合",
    version=__version__,
    lifespan=lifespan,
    # 互動式文件會列出所有端點與參數，由 ENABLE_API_DOCS 決定是否對外提供
    docs_url="/docs" if settings.ENABLE_API_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_API_DOCS else None
)
setup_middlewares(app)
app.include_router(auth.router, tags=["authentication"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(api_tools.router, prefix="/api/api-tools", tags=["api_tools"])
app.include_router(mcp.router, prefix="/api/mcp", tags=["mcp"])
app.include_router(tags_router.router, prefix="/api", tags=["tags"])
@app.get("/")
async def root():
    return {"message": "ChatBot API is running"}
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
def create_app():
    try:
        cuda_available = torch.cuda.is_available()
    except Exception:
        cuda_available = False
    logger.info(f"Startup status: torch.cuda.is_available() = {cuda_available}")
    try:
        import faiss
        faiss_gpu_available = hasattr(faiss, 'StandardGpuResources') and faiss.get_num_gpus() > 0
        logger.info(f"FAISS gpu available: {faiss_gpu_available}; num_gpus = {faiss.get_num_gpus() if faiss_gpu_available else 0}")
    except Exception as e:
        logger.warning("FAISS not importable or CPU-only. If you intended to use GPU FAISS, ensure faiss-gpu is installed and CUDA is configured. Error: %s", e)
        faiss_gpu_available = False
    return app
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run AskMiao ChatBot Backend API Server")
    parser.add_argument("--host", type=str, default=settings.HOST, help=f"Host address (default: {settings.HOST})")
    parser.add_argument("--port", type=int, default=settings.PORT, help=f"Port number (default: {settings.PORT})")
    parser.add_argument("--reload", action=argparse.BooleanOptionalAction, default=settings.RELOAD, help=f"Enable/disable auto-reload (default: RELOAD={settings.RELOAD})")
    args = parser.parse_args()
    reload_dirs = [os.path.join(BASE_DIR, "app")]
    reload_excludes = [
        "*.log", "*.db", "*.bin", "*.pkl", "*.sqlite*",
        "data", "logs", "data/*", "logs/*", "data/**", "logs/**"
    ]
    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=reload_dirs if args.reload else None,
        reload_excludes=reload_excludes if args.reload else None,
        app_dir=BASE_DIR,
        # 預設不採信 X-Forwarded-For：本機代理（例如 Vite）會原樣轉送用戶端自帶的標頭。
        # 前方有會覆寫該標頭的反向代理時，以 FORWARDED_ALLOW_IPS 明確指定信任的代理位址
        proxy_headers=bool(settings.FORWARDED_ALLOW_IPS),
        forwarded_allow_ips=settings.FORWARDED_ALLOW_IPS
    )
