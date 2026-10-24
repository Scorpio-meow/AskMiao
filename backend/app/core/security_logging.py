
import logging
import json
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import Request
import os
from app.core.limits import LOG_FILE_BACKUP_COUNT, LOG_FILE_MAX_BYTES, MAX_LOG_FIELD_CHARS
security_logger = logging.getLogger("security")
security_logger.setLevel(logging.INFO)
# 安全事件只寫 security.log，不再重複落地到 app.log
security_logger.propagate = False
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
security_log_file = os.path.join(log_dir, "security.log")
file_handler = RotatingFileHandler(
    security_log_file, maxBytes=LOG_FILE_MAX_BYTES, backupCount=LOG_FILE_BACKUP_COUNT, encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(formatter)
security_logger.addHandler(file_handler)
import re
SENSITIVE_KEYS = {
    "password",
    "pass",
    "passwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "cred",
    "credentials",
    "private_key",
    "ssn",
    "card_number",
    "credit_card",
    "cookie",
}
SENSITIVE_JSON_RE = re.compile(
    r'(?i)("(?:password|passwd|pass|secret|token|access_token|refresh_token|api_key|apikey|authorization|auth|credentials|cred|private_key)"\s*:\s*)"[^"]*"',
)
def truncate_log_value(value: Any) -> Any:
    """日誌中的字串欄位（含匿名請求可控的帳號名稱、User-Agent）限制長度"""
    if isinstance(value, str) and len(value) > MAX_LOG_FIELD_CHARS:
        return value[:MAX_LOG_FIELD_CHARS] + f"…(+{len(value) - MAX_LOG_FIELD_CHARS})"
    if isinstance(value, dict):
        return {truncate_log_value(k): truncate_log_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [truncate_log_value(item) for item in value]
    return value
def sanitize_sensitive_data(data: Any) -> Any:
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            key_str = str(key)
            key_lower = key_str.lower()
            if any(s in key_lower for s in SENSITIVE_KEYS):
                sanitized[key_str] = "[REDACTED]"
            else:
                sanitized[key_str] = sanitize_sensitive_data(value)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_sensitive_data(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(sanitize_sensitive_data(item) for item in data)
    return data
def log_security_event(
    event_type: str,
    request: Optional[Request] = None,
    user_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
    severity: str = "INFO"
):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "severity": severity,
        "user_id": user_id,
    }
    
    if request:
        log_entry.update({
            "client_ip": request.client.host if request.client else "unknown",
            "method": request.method,
            "path": request.url.path,
            "user_agent": request.headers.get("user-agent", "unknown"),
        })
    
    if details:
        log_entry["details"] = details
    
    sanitized_entry = truncate_log_value(sanitize_sensitive_data(log_entry))
    log_message = json.dumps(sanitized_entry, ensure_ascii=False)
    log_message = SENSITIVE_JSON_RE.sub(r'\1"[REDACTED]"', log_message)
    
    if severity == "CRITICAL":
        security_logger.critical(log_message)
    elif severity == "ERROR":
        security_logger.error(log_message)
    elif severity == "WARNING":
        security_logger.warning(log_message)
    else:
        security_logger.info(log_message)
