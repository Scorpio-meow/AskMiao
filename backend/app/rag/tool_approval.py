"""有副作用的工具在 Agent 迴圈中執行前，須由發問的使用者在對話內核准。

Agent 遇到需要核准的工具呼叫時，以 approval_required 事件把工具與參數送給前端並暫停；
使用者按下核准或拒絕後，前端呼叫 POST /api/chat/approvals/{approval_id}，這裡喚醒等待中的 Agent。
每個待核准項目綁定發問的使用者，其他使用者無法代為核准；逾時視為拒絕。
"""
import asyncio
import secrets
from typing import Dict, Optional, Tuple

# 自訂 API 工具中不改變伺服器狀態的 HTTP 方法；其他方法預設需要核准
SAFE_HTTP_METHODS = ("GET", "HEAD", "OPTIONS")
APPROVAL_TIMEOUT_SECONDS = 300


def default_requires_approval(method: Optional[str]) -> bool:
    return (method or "GET").upper() not in SAFE_HTTP_METHODS


class ToolApprovalBroker:
    def __init__(self) -> None:
        self._pending: Dict[str, Tuple[int, asyncio.Future]] = {}

    def create(self, user_id: int) -> Tuple[str, asyncio.Future]:
        approval_id = secrets.token_urlsafe(16)
        future = asyncio.get_running_loop().create_future()
        self._pending[approval_id] = (user_id, future)
        return approval_id, future

    def resolve(self, approval_id: str, user_id: int, approved: bool) -> bool:
        """只有建立該項目的使用者能核准；找不到、不屬於該使用者或已處理時回傳 False"""
        entry = self._pending.get(approval_id)
        if entry is None or entry[0] != user_id or entry[1].done():
            return False
        entry[1].set_result(bool(approved))
        return True

    def discard(self, approval_id: str) -> None:
        entry = self._pending.pop(approval_id, None)
        if entry is not None and not entry[1].done():
            entry[1].cancel()

    async def wait(self, approval_id: str, future: asyncio.Future) -> bool:
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=APPROVAL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            return False
        finally:
            self.discard(approval_id)


approval_broker = ToolApprovalBroker()
