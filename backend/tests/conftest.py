from datetime import datetime

import pytest


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
