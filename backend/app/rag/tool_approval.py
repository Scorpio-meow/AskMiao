import asyncio
import secrets
from typing import Dict, Optional, Tuple
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