
import secrets
from functools import lru_cache
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from datetime import datetime
from pydantic import ValidationError
from app.models import User
from app.core.jwt_auth import PasswordManager, validate_password_strength
from app.schemas.auth import UserRegister
@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    return PasswordManager.hash_password(secrets.token_urlsafe(16))
def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()
def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()
def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()
def get_user_by_username_or_email(db: Session, identifier: str) -> Optional[User]:
    return db.query(User).filter(
        or_(User.username == identifier, User.email == identifier)
    ).first()
def create_user(
    db: Session,
    username: str,
    email: str,
    password: str,
    role: str = "user",
    is_admin: bool = False
) -> User:
    hashed_password = PasswordManager.hash_password(password)
    now = datetime.utcnow()
    
    db_user = User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        role=role,
        is_admin=is_admin,
        is_active=True,
        created_at=now,
        tokens_valid_after=now
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user
def create_account(db: Session, username: str, email: str, password: str, is_admin: bool) -> User:
    try:
        validated = UserRegister(username=username, email=email, password=password)
    except ValidationError as e:
        raise ValueError("; ".join(error["msg"].removeprefix("Value error, ") for error in e.errors())) from e
    is_valid, error_msg = validate_password_strength(validated.password)
    if not is_valid:
        raise ValueError(error_msg)
    if get_user_by_username(db, validated.username):
        raise ValueError("使用者名稱已被使用")
    if get_user_by_email(db, validated.email):
        raise ValueError("電子郵件已被使用")
    return create_user(
        db=db,
        username=validated.username,
        email=validated.email,
        password=validated.password,
        role="admin" if is_admin else "user",
        is_admin=is_admin,
    )
def authenticate_user(
    db: Session,
    username_or_email: str,
    password: str
) -> Optional[User]:
    user = get_user_by_username_or_email(db, username_or_email)

    if user is None or not user.is_active:
        # 帳號不存在或已停用時也驗一次密碼，回應時間才不會透露帳號是否存在
        PasswordManager.verify_password(password, _dummy_password_hash())
        return None

    if not PasswordManager.verify_password(password, user.hashed_password):
        return None
    if PasswordManager.needs_rehash(user.hashed_password):
        user.hashed_password = PasswordManager.hash_password(password)
        db.commit()
        db.refresh(user)
    
    return user
def update_user_password(
    db: Session,
    user_id: int,
    new_password: str
) -> Optional[User]:
    user = get_user_by_id(db, user_id)
    
    if not user:
        return None
    
    user.hashed_password = PasswordManager.hash_password(new_password)
    # 變更密碼後，所有已簽發的存取與重新整理權杖（含其他裝置與可能外洩者）一律失效
    user.tokens_valid_after = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    return user
def update_user_email(
    db: Session,
    user_id: int,
    new_email: str
) -> Optional[User]:
    user = get_user_by_id(db, user_id)
    
    if not user:
        return None
    
    user.email = new_email
    db.commit()
    db.refresh(user)
    
    return user
def update_user_last_login(
    db: Session,
    user_id: int
) -> Optional[User]:
    user = get_user_by_id(db, user_id)
    
    if not user:
        return None
    
    user.last_login = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    return user