"""建立帳號（含第一位管理員）。

ALLOW_REGISTRATION=false 時，帳號一律由管理員以此腳本建立。密碼以互動方式輸入，
不經命令列參數，避免留在殼層歷史與行程清單中。在 backend/ 下執行：

    python scripts/create_user.py --username alice --email alice@example.com
    python scripts/create_user.py --username root --email root@example.com --admin
"""
import argparse
import getpass
import os
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.jwt_auth import validate_password_strength
from app.crud.crud_user import create_user, get_user_by_email, get_user_by_username
from app.models import User
from app.models.database import Base, SessionLocal, engine, upgrade_schema
from app.schemas.auth import UserRegister


def create_account(db: Session, username: str, email: str, password: str, is_admin: bool) -> User:
    """套用與自行註冊相同的使用者名稱、電子郵件與密碼規則；不符合時拋出 ValueError"""
    try:
        validated = UserRegister(username=username, email=email, password=password)
    except ValidationError as e:
        raise ValueError("; ".join(error["msg"] for error in e.errors())) from e
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


def main() -> int:
    parser = argparse.ArgumentParser(description="建立 AskMiao 帳號")
    parser.add_argument("--username", required=True, help="使用者名稱（3～50 字，只含字母、數字、底線與連字號）")
    parser.add_argument("--email", required=True, help="電子郵件")
    parser.add_argument("--admin", action="store_true", help="建立為管理員")
    args = parser.parse_args()

    password = getpass.getpass("密碼：")
    if password != getpass.getpass("再次輸入密碼："):
        print("兩次輸入的密碼不一致", file=sys.stderr)
        return 1

    Base.metadata.create_all(bind=engine)
    upgrade_schema()
    with SessionLocal() as db:
        try:
            user = create_account(db, args.username, args.email, password, args.admin)
        except ValueError as e:
            print(f"建立失敗：{e}", file=sys.stderr)
            return 1
    print(f"已建立{'管理員' if user.is_admin else '使用者'} {user.username}（id {user.id}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
