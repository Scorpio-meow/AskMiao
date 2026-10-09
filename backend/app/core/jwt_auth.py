
import calendar
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging
import bcrypt as bcrypt_lib
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models import User
from app.models.database import get_db
logger = logging.getLogger(__name__)
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS
ALGORITHM = "RS256"
# RSA 金鑰無法載入時一律拒絕啟動，不退回以共用密鑰簽署的演算法
from app.core.rsa_keys import rsa_manager
RSA_PRIVATE_KEY = rsa_manager.get_private_key_pem()
RSA_PUBLIC_KEY = rsa_manager.get_public_key_pem()
try:
    from app.core.redis_client import TokenBlacklist
    USE_BLACKLIST = True
except Exception as e:
    USE_BLACKLIST = False
    print(f"Token 黑名單功能不可用: {e}")
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
security = HTTPBearer()
def _numeric_date(moment: datetime) -> float:
    """UTC 時刻轉成 JWT 的 NumericDate 並保留微秒（RFC 7519 允許小數）。

    撤銷以 tokens_valid_after 比對簽發時間；只取整秒時，與變更密碼同一秒內稍早簽發的權杖仍然有效，
    持有外洩重新整理權杖的人每秒換發一次就能一直保住工作階段。
    """
    return calendar.timegm(moment.utctimetuple()) + moment.microsecond / 1_000_000
def _normalize_legacy_bcrypt_password(password: str, max_bytes: int = 72) -> str:
    encoded_password = password.encode("utf-8")
    if len(encoded_password) <= max_bytes:
        return password
    return encoded_password[:max_bytes].decode("utf-8", errors="ignore")
class PasswordManager:
    
    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        if hashed_password.startswith("$2"):
            plain_password = _normalize_legacy_bcrypt_password(plain_password)
            try:
                return bcrypt_lib.checkpw(
                    plain_password.encode("utf-8"),
                    hashed_password.encode("utf-8"),
                )
            except ValueError:
                return False
        return pwd_context.verify(plain_password, hashed_password)
    @staticmethod
    def needs_rehash(hashed_password: str) -> bool:
        return hashed_password.startswith("$2") or pwd_context.needs_update(hashed_password)
class TokenManager:
    
    @staticmethod
    def create_access_token(
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({
            "exp": expire,
            "type": "access",
            "iat": _numeric_date(datetime.utcnow())
        })
        
        return jwt.encode(to_encode, RSA_PRIVATE_KEY, algorithm=ALGORITHM)
    
    @staticmethod
    def create_refresh_token(
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
        to_encode.update({
            "exp": expire,
            "type": "refresh",
            "iat": _numeric_date(datetime.utcnow())
        })
        
        return jwt.encode(to_encode, RSA_PRIVATE_KEY, algorithm=ALGORITHM)
    
    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        if USE_BLACKLIST and TokenBlacklist.is_blacklisted(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="權杖已被撤銷",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        try:
            return jwt.decode(
                token,
                RSA_PUBLIC_KEY,
                algorithms=[ALGORITHM],
                options={"verify_signature": True, "verify_exp": True}
            )
        except JWTError:
            logger.exception("無效的認證令牌: 驗證失敗")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="認證權杖無效：驗證失敗",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    @staticmethod
    def decode_token_ignoring_expiry(token: str) -> Dict[str, Any]:
        """只驗簽章、不檢查到期：登出時存取權杖可能已過期，仍要據此確認請求者並撤銷其重新整理權杖"""
        try:
            return jwt.decode(
                token,
                RSA_PUBLIC_KEY,
                algorithms=[ALGORITHM],
                options={"verify_signature": True, "verify_exp": False}
            )
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="認證權杖無效：驗證失敗",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    @staticmethod
    def verify_token_type(payload: Dict[str, Any], expected_type: str) -> bool:
        return payload.get("type") == expected_type
def resolve_token_user(db: Session, payload: Dict[str, Any]) -> User:
    """把已驗簽的權杖綁定到資料庫中的現存帳號。

    帳號不存在、已停用，或權杖簽發早於帳號的 tokens_valid_after（帳號建立時間，
    防止刪除後 id 被重用；變更密碼時更新為當下）都視為無效；
    身分與權限一律取自資料庫，不信任權杖內的聲明。
    """
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="認證權杖無效：驗證失敗",
        headers={"WWW-Authenticate": "Bearer"},
    )
    sub = payload.get("sub")
    issued_at = payload.get("iat")
    if sub is None or not isinstance(issued_at, (int, float)):
        raise invalid
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise invalid
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active or user.tokens_valid_after is None:
        raise invalid
    if issued_at < _numeric_date(user.tokens_valid_after):
        raise invalid
    return user
def get_current_user_from_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    token = credentials.credentials
    payload = TokenManager.decode_token(token)

    if not TokenManager.verify_token_type(payload, "access"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="權杖類型無效",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = resolve_token_user(db, payload)
    return {
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "is_admin": bool(user.is_admin)
    }
async def get_current_active_user(
    current_user: Dict[str, Any] = Depends(get_current_user_from_token)
) -> Dict[str, Any]:
    return current_user
async def get_current_admin_user(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理員權限"
        )
    
    return current_user
def create_token_pair(user_data: Dict[str, Any]) -> Dict[str, str]:
    token_data = {
        "sub": str(user_data["user_id"]),
        "username": user_data.get("username"),
        "email": user_data.get("email"),
        "role": user_data.get("role", "user"),
        "is_admin": user_data.get("is_admin", False)
    }
    
    access_token = TokenManager.create_access_token(token_data)
    refresh_token = TokenManager.create_refresh_token({"sub": str(user_data["user_id"])})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }
def verify_refresh_token(token: str) -> Dict[str, Any]:
    payload = TokenManager.decode_token(token)
    
    if not TokenManager.verify_token_type(payload, "refresh"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="重新整理權杖類型無效"
        )
    
    return payload
def validate_password_strength(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "密碼長度至少需要 8 個字元"
    
    if not any(c.isupper() for c in password):
        return False, "密碼必須包含至少一個大寫字母"
    
    if not any(c.islower() for c in password):
        return False, "密碼必須包含至少一個小寫字母"
    
    if not any(c.isdigit() for c in password):
        return False, "密碼必須包含至少一個數字"
    
    return True, ""
def sanitize_username(username: str) -> str:
    import re
    return re.sub(r'[^\w\-]', '', username)
def revoke_token(token: str, expires_in: int = None):
    if not USE_BLACKLIST:
        print("Token 黑名單功能未啟用")
        return False
    
    try:
        if expires_in is None:
            payload = TokenManager.decode_token(token)
            exp = payload.get("exp")
            if exp:
                expires_in = max(int(exp - datetime.utcnow().timestamp()), 0)
            else:
                expires_in = 86400
        
        return TokenBlacklist.add_token(token, expires_in)
    except Exception as e:
        print(f"撤銷 Token 失敗: {e}")
        return False
