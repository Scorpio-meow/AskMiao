import hashlib
import heapq
import time
import logging
import threading
from typing import Dict, List, Tuple
from app.core.limits import MAX_REVOKED_TOKENS
logger = logging.getLogger(__name__)
class TokenBlacklist:
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