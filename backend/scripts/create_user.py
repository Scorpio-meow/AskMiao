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

from app.crud.crud_user import create_account
from app.models.database import Base, SessionLocal, engine, upgrade_schema


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
