import json
import logging
from typing import Any, Callable, Dict, Optional, Tuple
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import settings
from app.core.error_response import SafeClientError
logger = logging.getLogger(__name__)
ENCRYPTED_PREFIX = "fernet:"
SECRET_MASK = "••••••••"
NON_SECRET_HEADER_NAMES = {"accept", "accept-encoding", "accept-language", "cache-control", "content-type", "user-agent"}
SECRET_AUTH_CONFIG_KEYS = {"token", "key_value", "password", "client_secret"}
_fernet = Fernet(settings.TOOL_SECRETS_KEY.encode("ascii"))
def is_encrypted(stored: str) -> bool:
    return stored.startswith(ENCRYPTED_PREFIX)
def encrypt_json(value: Optional[Dict[str, Any]]) -> Optional[str]:
    if not value:
        return None
    token = _fernet.encrypt(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    return ENCRYPTED_PREFIX + token.decode("ascii")
def decrypt_json(stored: Optional[str]) -> Optional[Dict[str, Any]]:
    if stored is None:
        return None
    if not is_encrypted(stored):
        raise SafeClientError("工具憑證欄位未加密：重新啟動後端時會加密既有資料")
    try:
        plaintext = _fernet.decrypt(stored[len(ENCRYPTED_PREFIX):].encode("ascii"))
    except InvalidToken as e:
        raise SafeClientError("無法以目前的 TOOL_SECRETS_KEY 解密工具憑證，請重新輸入") from e
    return json.loads(plaintext)
def decrypt_for_display(stored: Optional[str]) -> Tuple[Optional[Dict[str, Any]], bool]:
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
    return True
def mask(values: Optional[Dict[str, Any]], is_secret: Callable[[str], bool]) -> Optional[Dict[str, Any]]:
    if values is None:
        return None
    return {name: SECRET_MASK if is_secret(name) and value not in (None, "") else value for name, value in values.items()}
def merge_masked(incoming: Dict[str, Any], existing: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = {}
    for name, value in incoming.items():
        if value == SECRET_MASK:
            if existing is None or name not in existing:
                raise SafeClientError(f"欄位 {name} 沒有已儲存的值，請輸入實際內容")
            merged[name] = existing[name]
        else:
            merged[name] = value
    return merged