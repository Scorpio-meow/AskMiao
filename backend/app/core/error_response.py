"""統一的對外錯誤回應處理。

完整例外訊息與堆疊僅寫入伺服器端日誌，對外只回傳一組隨機錯誤代碼，
使用者回報該代碼後即可在日誌中定位原始例外，避免洩漏內部結構
(CWE-209 / CWE-497)。
"""
import logging
import uuid
from typing import Any, Dict

GENERIC_ERROR_MESSAGE = "伺服器內部錯誤，請聯繫系統管理員並提供錯誤代碼"


class SafeClientError(ValueError):
    """訊息內容已確認僅描述使用者輸入本身、不含伺服器內部資訊，可原樣回傳客戶端。

    用於輸入驗證類錯誤（例如使用者提供的規格格式不合法），
    讓使用者得到可據以修正的診斷訊息；其餘未預期例外一律走
    ``build_error_payload`` 的錯誤代碼機制。

    繼承 ``ValueError`` 以維持既有呼叫端與測試對輸入錯誤的攔截行為。
    """


def log_and_get_error_id(
    logger: logging.Logger,
    context: str,
    exc: BaseException,
    level: int = logging.ERROR,
) -> str:
    """將完整例外（含堆疊）寫入伺服器日誌，並回傳對外可揭露的錯誤代碼。"""
    error_id = uuid.uuid4().hex[:12]
    logger.log(level, "[%s] %s", error_id, context, exc_info=exc)
    return error_id


def format_client_error(error_id: str) -> str:
    """組出不含任何內部細節的對外錯誤訊息。"""
    return f"{GENERIC_ERROR_MESSAGE}（錯誤代碼：{error_id}）"


def build_error_payload(
    logger: logging.Logger,
    context: str,
    exc: BaseException,
    level: int = logging.ERROR,
) -> Dict[str, Any]:
    """記錄例外並產生可安全回傳給前端的錯誤內容。"""
    error_id = log_and_get_error_id(logger, context, exc, level)
    return {"detail": format_client_error(error_id), "error_id": error_id}
