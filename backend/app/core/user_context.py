from fastapi import Depends
from app.core.jwt_auth import get_current_active_user
async def get_current_user_id(
    user: dict = Depends(get_current_active_user)
) -> int:
    return user["user_id"]
