"""外部工具憑證的靜態加密與管理 API 回應的遮蔽。

自訂 API 工具的 headers、auth_config 與 MCP 伺服器的 env_vars、headers 含 API 金鑰等憑證：
寫入資料庫前以 TOOL_SECRETS_KEY（Fernet）加密，資料庫或備份外流時不會直接暴露憑證。
管理 API 的回應以 SECRET_MASK 取代秘密值，更新時仍為 SECRET_MASK 的欄位沿用原本的值，
因此憑證寫入後不會再從 API 讀出（管理員的瀏覽器工作階段被盜用時也拿不到）。
"""
import json
import logging
from typing import Any, Callable, Dict, Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.error_response import SafeClientError

logger = logging.getLogger(__name__)

ENCRYPTED_PREFIX = "fernet:"
SECRET_MASK = "••••••••"
# 這些標頭的值不是憑證：回應中不遮蔽，工具結果也不做替換（避免把回應中的一般字詞一併換掉）
NON_SECRET_HEADER_NAMES = {"accept", "accept-encoding", "accept-language", "cache-control", "content-type", "user-agent"}
# auth_config 中屬於憑證的鍵；key_name、key_in、username 等設定照常顯示
SECRET_AUTH_CONFIG_KEYS = {"token", "key_value", "password"}

_fernet = Fernet(settings.TOOL_SECRETS_KEY.encode("ascii"))


def is_encrypted(stored: str) -> bool:
    return stored.startswith(ENCRYPTED_PREFIX)


def encrypt_json(value: Optional[Dict[str, Any]]) -> Optional[str]:
    if not value:
        return None
    token = _fernet.encrypt(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    return ENCRYPTED_PREFIX + token.decode("ascii")


def decrypt_json(stored: Optional[str]) -> Optional[Dict[str, Any]]:
    """解密欄位；未加密或無法以目前的金鑰解密時拋出 ValueError"""
    if stored is None:
        return None
    if not is_encrypted(stored):
        raise ValueError("工具憑證欄位未加密：重新啟動後端時會加密既有資料")
    try:
        plaintext = _fernet.decrypt(stored[len(ENCRYPTED_PREFIX):].encode("ascii"))
    except InvalidToken as e:
        raise ValueError("無法以目前的 TOOL_SECRETS_KEY 解密工具憑證，請重新輸入") from e
    return json.loads(plaintext)


def decrypt_for_display(stored: Optional[str]) -> Tuple[Optional[Dict[str, Any]], bool]:
    """供管理 API 顯示用：回傳 (解密結果, 是否無法解密)。無法解密時讓管理員重新輸入，而不是整頁失敗"""
    try:
        return decrypt_json(stored), False
    except ValueError as e:
        logger.warning("工具憑證無法解密: %s", e)
        return None, True


def is_secret_header(name: str) -> bool:
    return name.lower() not in NON_SECRET_HEADER_NAMES


def is_secret_auth_key(name: str) -> bool:
    return name in SECRET_AUTH_CONFIG_KEYS


def is_any_key(name: str) -> bool:
    """MCP 的環境變數一律視為憑證"""
    return True


def mask(values: Optional[Dict[str, Any]], is_secret: Callable[[str], bool]) -> Optional[Dict[str, Any]]:
    if values is None:
        return None
    return {name: SECRET_MASK if is_secret(name) and value not in (None, "") else value for name, value in values.items()}


def merge_masked(incoming: Dict[str, Any], existing: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """以 incoming 取代整個欄位；其中仍為 SECRET_MASK 的鍵沿用 existing 的值"""
    merged = {}
    for name, value in incoming.items():
        if value == SECRET_MASK:
            if existing is None or name not in existing:
                raise SafeClientError(f"欄位 {name} 沒有已儲存的值，請輸入實際內容")
            merged[name] = existing[name]
        else:
            merged[name] = value
    return merged
