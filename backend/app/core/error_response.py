import logging
import uuid
from typing import Any, Dict
from app.core.request_context import current_request_id
GENERIC_ERROR_MESSAGE = "伺服器內部錯誤，請聯絡系統管理員並提供錯誤代碼"
class SafeClientError(ValueError):
    pass
def log_and_get_error_id(
    logger: logging.Logger,
    context: str,
    exc: BaseException,
    level: int = logging.ERROR,
) -> str:
    error_id = uuid.uuid4().hex[:12]
    logger.log(level, "[%s] %s", error_id, context, exc_info=exc)
    return error_id
def format_client_error(error_id: str) -> str:
    return f"{GENERIC_ERROR_MESSAGE}（錯誤代碼：{error_id}）"
def format_ssrf_rejection(error_id: str) -> str:
    return (
        "SSRF 防護拒絕連線：網址或其轉址目標未通過安全檢查，完整原因記錄於伺服器日誌"
        f"（錯誤代碼：{error_id}）"
    )
def build_error_payload(
    logger: logging.Logger,
    context: str,
    exc: BaseException,
    level: int = logging.ERROR,
) -> Dict[str, Any]:
    error_id = log_and_get_error_id(logger, context, exc, level)
    return {"detail": format_client_error(error_id), "error_id": error_id, "request_id": current_request_id()}