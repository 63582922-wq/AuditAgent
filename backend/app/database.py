from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_lightweight_migrations()


def _ensure_lightweight_migrations():
    """开发环境 SQLite 增量列迁移（生产请用 alembic upgrade head）。"""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if not insp.has_table("memories"):
        return
    cols = {c["name"] for c in insp.get_columns("memories")}
    if "embedding_json" not in cols:
        with engine.begin() as conn:
            if settings.database_url.startswith("sqlite"):
                conn.execute(text("ALTER TABLE memories ADD COLUMN embedding_json JSON"))
            else:
                conn.execute(text("ALTER TABLE memories ADD COLUMN embedding_json JSONB"))
