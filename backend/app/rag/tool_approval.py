import asyncio
import secrets
from typing import Any, Dict, Optional, Tuple
SAFE_HTTP_METHODS = ("GET", "HEAD", "OPTIONS")
APPROVAL_TIMEOUT_SECONDS = 300
APPROVAL = "approval"
QUESTION = "question"
def default_requires_approval(method: Optional[str]) -> bool:
    return (method or "GET").upper() not in SAFE_HTTP_METHODS
class ToolApprovalBroker:
    def __init__(self) -> None:
        self._pending: Dict[str, Tuple[int, str, asyncio.Future]] = {}
    def _open(self, user_id: int, kind: str) -> Tuple[str, asyncio.Future]:
        token = secrets.token_urlsafe(16)
        future = asyncio.get_running_loop().create_future()
        self._pending[token] = (user_id, kind, future)
        return token, future
    def _settle(self, token: str, user_id: int, kind: str, value: Any) -> bool:
        entry = self._pending.get(token)
        if entry is None or entry[0] != user_id or entry[1] != kind or entry[2].done():
            return False
        entry[2].set_result(value)
        return True
    def create(self, user_id: int) -> Tuple[str, asyncio.Future]:
        return self._open(user_id, APPROVAL)
    def create_question(self, user_id: int) -> Tuple[str, asyncio.Future]:
        return self._open(user_id, QUESTION)
    def resolve(self, approval_id: str, user_id: int, approved: bool, remember: bool) -> bool:
        return self._settle(approval_id, user_id, APPROVAL, (bool(approved), bool(approved and remember)))
    def answer(self, question_id: str, user_id: int, answer: str) -> bool:
        return self._settle(question_id, user_id, QUESTION, answer)
    def discard(self, token: str) -> None:
        entry = self._pending.pop(token, None)
        if entry is not None and not entry[2].done():
            entry[2].cancel()
    async def _wait(self, token: str, future: asyncio.Future, on_timeout: Any) -> Any:
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=APPROVAL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            return on_timeout
        finally:
            self.discard(token)
    async def wait(self, approval_id: str, future: asyncio.Future) -> Tuple[bool, bool]:
        return await self._wait(approval_id, future, (False, False))
    async def wait_answer(self, question_id: str, future: asyncio.Future) -> Optional[str]:
        return await self._wait(question_id, future, None)
approval_broker = ToolApprovalBroker()