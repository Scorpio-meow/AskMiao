import hashlib
import heapq
import time
import logging
import threading
from typing import Dict, List, Optional, Tuple
from app.core.limits import MAX_REVOKED_TOKENS
logger = logging.getLogger(__name__)
class TokenBlacklist:
    """記憶體型 Token 黑名單管理器（無須外部 Redis 依賴）

    以權杖的 SHA-256 為鍵（固定大小），到期時間另存於最小堆積：每次操作只清掉堆頂已到期的條目，
    不再逐筆掃描整份名單。條目數超過 MAX_REVOKED_TOKENS 時淘汰最早到期的條目。
    """
    _blacklist: Dict[str, float] = {}
    _expiry_heap: List[Tuple[float, str]] = []
    _lock = threading.Lock()
    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
    @classmethod
    def _cleanup_expired(cls, now: float):
        while cls._expiry_heap and cls._expiry_heap[0][0] <= now:
            expires_at, key = heapq.heappop(cls._expiry_heap)
            if cls._blacklist.get(key) == expires_at:
                del cls._blacklist[key]
    @classmethod
    def _evict_until_within_limit(cls):
        while len(cls._blacklist) > MAX_REVOKED_TOKENS and cls._expiry_heap:
            expires_at, key = heapq.heappop(cls._expiry_heap)
            if cls._blacklist.get(key) == expires_at:
                del cls._blacklist[key]
                logger.warning("權杖撤銷名單已達上限，淘汰最早到期的條目")
    @classmethod
    def add_token(cls, token: str, expires_in: int = 3600) -> bool:
        try:
            now = time.time()
            key = cls._key(token)
            expires_at = now + max(1, expires_in)
            with cls._lock:
                cls._cleanup_expired(now)
                cls._blacklist[key] = expires_at
                heapq.heappush(cls._expiry_heap, (expires_at, key))
                cls._evict_until_within_limit()
            return True
        except Exception as e:
            logger.error(f"加入黑名單失敗: {e}")
            return False
    @classmethod
    def is_blacklisted(cls, token: str) -> bool:
        try:
            now = time.time()
            key = cls._key(token)
            with cls._lock:
                cls._cleanup_expired(now)
                expires_at = cls._blacklist.get(key)
                return expires_at is not None and expires_at > now
        except Exception as e:
            logger.error(f"檢查黑名單失敗: {e}")
            return False
    @classmethod
    def remove_token(cls, token: str) -> bool:
        try:
            with cls._lock:
                cls._blacklist.pop(cls._key(token), None)
            return True
        except Exception as e:
            logger.error(f"移除黑名單失敗: {e}")
            return False
def init_redis():
    """向下相容保留，直接回傳 True"""
    logger.info("Token 黑名單已採用記憶體模式運行 (無需 Redis)")
    return True
def get_redis() -> Optional[object]:
    """向下相容保留"""
    return None
def close_redis():
    """向下相容保留"""
    pass
