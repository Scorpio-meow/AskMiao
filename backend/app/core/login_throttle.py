"""登入失敗節流。

同一個登入識別（帳號名稱或電子郵件）與同一個來源位址各自計數：在 LOGIN_FAILURE_WINDOW_SECONDS
秒內失敗達門檻，該識別或位址的登入暫停 LOGIN_LOCKOUT_SECONDS 秒。依帳號計數擋下分散來源的
密碼猜測，依位址計數擋下單一來源對多個帳號的嘗試；鎖定只影響登入，且到期自動解除。
不存在的帳號同樣計數，回應與存在的帳號一致。
"""
import math
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Optional

from app.core.config import settings
from app.core.limits import MAX_TRACKED_ADDRESSES, MAX_TRACKED_LOGIN_ACCOUNTS


@dataclass
class _FailureRecord:
    failures: Deque[float] = field(default_factory=deque)
    locked_until: float = 0.0


class _FailureTracker:
    """以鍵分組的失敗時間視窗；追蹤的鍵數有上限，最久未活動的先淘汰"""

    def __init__(self, max_failures: int, window_seconds: int, lockout_seconds: int, max_keys: int):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self.max_keys = max_keys
        self._records: "OrderedDict[str, _FailureRecord]" = OrderedDict()

    def retry_after(self, key: str, now: float) -> float:
        record = self._records.get(key)
        if record is None or record.locked_until <= now:
            return 0.0
        return record.locked_until - now

    def record_failure(self, key: str, now: float) -> bool:
        """記錄一次失敗；剛達到門檻而進入鎖定時回傳 True"""
        record = self._records.get(key)
        if record is None:
            record = _FailureRecord()
            self._records[key] = record
            while len(self._records) > self.max_keys:
                self._records.popitem(last=False)
        else:
            self._records.move_to_end(key)
        cutoff = now - self.window_seconds
        while record.failures and record.failures[0] <= cutoff:
            record.failures.popleft()
        record.failures.append(now)
        if len(record.failures) >= self.max_failures:
            record.failures.clear()
            record.locked_until = now + self.lockout_seconds
            return True
        return False

    def clear(self, key: str) -> None:
        self._records.pop(key, None)


class LoginThrottle:
    def __init__(
        self,
        max_failures_per_account: int,
        max_failures_per_address: int,
        window_seconds: int,
        lockout_seconds: int,
        clock: Callable[[], float],
    ):
        self._accounts = _FailureTracker(max_failures_per_account, window_seconds, lockout_seconds, MAX_TRACKED_LOGIN_ACCOUNTS)
        self._addresses = _FailureTracker(max_failures_per_address, window_seconds, lockout_seconds, MAX_TRACKED_ADDRESSES)
        self._clock = clock
        self._lock = threading.Lock()

    @staticmethod
    def account_key(identifier: str) -> str:
        # 大小寫與前後空白不同的寫法視為同一個識別，避免以變化寫法繞過計數
        return identifier.strip().lower()

    def retry_after(self, identifier: str, address: Optional[str]) -> int:
        """仍在鎖定中時回傳需要等待的秒數（無條件進位），否則回傳 0"""
        now = self._clock()
        with self._lock:
            wait = self._accounts.retry_after(self.account_key(identifier), now)
            if address is not None:
                wait = max(wait, self._addresses.retry_after(address, now))
        return math.ceil(wait)

    def record_failure(self, identifier: str, address: Optional[str]) -> bool:
        """記錄一次登入失敗；帳號或位址因此進入鎖定時回傳 True"""
        now = self._clock()
        with self._lock:
            locked = self._accounts.record_failure(self.account_key(identifier), now)
            if address is not None:
                locked = self._addresses.record_failure(address, now) or locked
        return locked

    def record_success(self, identifier: str) -> None:
        """登入成功只清除該帳號的失敗紀錄；同一位址對其他帳號的失敗仍然計數"""
        with self._lock:
            self._accounts.clear(self.account_key(identifier))


login_throttle = LoginThrottle(
    max_failures_per_account=settings.LOGIN_MAX_FAILURES_PER_ACCOUNT,
    max_failures_per_address=settings.LOGIN_MAX_FAILURES_PER_ADDRESS,
    window_seconds=settings.LOGIN_FAILURE_WINDOW_SECONDS,
    lockout_seconds=settings.LOGIN_LOCKOUT_SECONDS,
    clock=time.monotonic,
)
