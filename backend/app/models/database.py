import os
from sqlalchemy import create_engine, MetaData, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
DATABASE_URL = settings.DATABASE_URL
POOL_SIZE = settings.DB_POOL_SIZE
MAX_OVERFLOW = settings.DB_MAX_OVERFLOW
POOL_RECYCLE = settings.DB_POOL_RECYCLE
POOL_PRE_PING = settings.DB_POOL_PRE_PING
ECHO_SQL = settings.SQLALCHEMY_ECHO
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False},
        echo=ECHO_SQL,
        pool_size=5,
        max_overflow=10,
        pool_recycle=POOL_RECYCLE
    )
else:
    engine = create_engine(
        DATABASE_URL,
        echo=ECHO_SQL,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_recycle=POOL_RECYCLE,
        pool_pre_ping=POOL_PRE_PING,
        pool_use_lifo=True
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
# 既有資料庫缺少的欄位：(資料表, 欄位, 型別, 補值 SQL)。create_all 不會替已存在的資料表加欄位
COLUMN_UPGRADES = (
    (
        "custom_api_tools",
        "requires_approval",
        "BOOLEAN",
        "UPDATE custom_api_tools SET requires_approval = "
        "(UPPER(COALESCE(method, 'GET')) NOT IN ('GET', 'HEAD', 'OPTIONS'))",
    ),
    ("mcp_servers", "requires_approval", "BOOLEAN", "UPDATE mcp_servers SET requires_approval = TRUE"),
    # 既有帳號沿用原本「權杖不得早於帳號建立時間」的規則
    ("users", "tokens_valid_after", "TIMESTAMP", "UPDATE users SET tokens_valid_after = created_at"),
)
def upgrade_schema(target_engine=None) -> None:
    target_engine = target_engine or engine
    inspector = inspect(target_engine)
    tables = set(inspector.get_table_names())
    with target_engine.begin() as conn:
        for table, column, column_type, backfill in COLUMN_UPGRADES:
            if table not in tables:
                continue
            if column in {c["name"] for c in inspector.get_columns(table)}:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"))
            conn.execute(text(backfill))
async def create_tables():
    Base.metadata.create_all(bind=engine)
    upgrade_schema()
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
