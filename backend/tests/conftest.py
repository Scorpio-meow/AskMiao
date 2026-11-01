from datetime import datetime

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolated_log_dir(tmp_path_factory):
    from app.core.config import settings
    from app.core.security_logging import ensure_security_log_handler, security_file_handlers, security_logger

    assert not security_file_handlers(), "安全日誌 handler 在測試改寫 LOG_DIR 之前就已建立"
    original_log_dir = settings.LOG_DIR
    log_dir = tmp_path_factory.mktemp("logs")
    settings.LOG_DIR = str(log_dir)
    ensure_security_log_handler()
    yield log_dir
    for handler in security_file_handlers():
        security_logger.removeHandler(handler)
        handler.close()
    settings.LOG_DIR = original_log_dir


@pytest.fixture
def existing_users():
    from sqlalchemy import text

    from app.models import User
    from app.models.database import Base, SessionLocal, engine

    def ensure(*users):
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            for user in users:
                if db.get(User, user["user_id"]) is None:
                    name = f"fixture-user-{user['user_id']}"
                    db.add(User(id=user["user_id"], username=name, email=f"{name}@example.com", hashed_password="x",
                                is_active=True, is_admin=user["is_admin"], role=user["role"],
                                created_at=datetime.utcnow(), tokens_valid_after=datetime.utcnow()))
            db.commit()
            if engine.dialect.name == "postgresql":
                db.execute(text("SELECT setval(pg_get_serial_sequence('users', 'id'), (SELECT MAX(id) FROM users))"))
                db.commit()

    return ensure
