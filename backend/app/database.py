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


MEETING_FK_TABLES = (
    "files",
    "parsed_documents",
    "extracted_entities",
    "risks",
    "outputs",
    "agent_run_logs",
    "agent_action_proposals",
    "analysis_jobs",
    "record_links",
)


def _ensure_lightweight_migrations():
    """开发环境 SQLite 增量列迁移（生产请用 alembic upgrade head）。"""
    import uuid

    from sqlalchemy import inspect, text

    insp = inspect(engine)

    if insp.has_table("memories"):
        cols = {c["name"] for c in insp.get_columns("memories")}
        if "embedding_json" not in cols:
            with engine.begin() as conn:
                if settings.database_url.startswith("sqlite"):
                    conn.execute(text("ALTER TABLE memories ADD COLUMN embedding_json JSON"))
                else:
                    conn.execute(text("ALTER TABLE memories ADD COLUMN embedding_json JSONB"))

    if not insp.has_table("projects"):
        return

    _ensure_meetings_schema(insp, text, uuid)


def _ensure_meetings_schema(insp, text, uuid):
    """004_meetings 的轻量等价迁移：meetings 表 + meeting_id 列 + 回填。"""
    import json

    from app import models  # noqa: F401

    if not insp.has_table("meetings"):
        Base.metadata.tables["meetings"].create(bind=engine, checkfirst=True)

    for table in MEETING_FK_TABLES:
        if not insp.has_table(table):
            continue
        cols = {c["name"] for c in insp.get_columns(table)}
        if "meeting_id" not in cols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN meeting_id VARCHAR(36)"))

    with engine.begin() as conn:
        projects = conn.execute(
            text("SELECT id, name, status, state_json, summary FROM projects")
        ).fetchall()
        for row in projects:
            pid, name, status, state_json, summary = row
            if isinstance(state_json, str):
                try:
                    state = json.loads(state_json) if state_json else {}
                except json.JSONDecodeError:
                    state = {}
            else:
                state = state_json or {}
            meeting_case = state.get("meeting_case") or {}
            meeting_code = str(meeting_case.get("meeting_code") or "DEFAULT").strip() or "DEFAULT"
            existing = conn.execute(
                text(
                    "SELECT id FROM meetings WHERE project_id = :pid AND meeting_code = :code LIMIT 1"
                ),
                {"pid": pid, "code": meeting_code[:64]},
            ).first()
            if existing:
                mid = existing[0]
            else:
                mid = str(uuid.uuid4())
                deliverable = state.get("deliverable")
                m_state = {
                    k: state.get(k)
                    for k in (
                        "meeting_case",
                        "missing_documents",
                        "present_categories",
                        "agent_plan",
                        "execution_graph",
                        "mission",
                        "sub_agent_briefs",
                        "synthesis_brief",
                        "runtime",
                        "runtime_live",
                        "execution_mode",
                        "agent_domain",
                        "processed_file_ids",
                    )
                    if state.get(k) is not None
                }
                if meeting_case and "meeting_case" not in m_state:
                    m_state["meeting_case"] = meeting_case
                conn.execute(
                    text(
                        """
                        INSERT INTO meetings (
                            id, project_id, meeting_code, meeting_title, observation_type,
                            meeting_type, status, summary, state_json, deliverable_json,
                            created_at, updated_at
                        ) VALUES (
                            :id, :project_id, :meeting_code, :meeting_title, :observation_type,
                            :meeting_type, :status, :summary, :state_json, :deliverable_json,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "id": mid,
                        "project_id": pid,
                        "meeting_code": meeting_code[:64],
                        "meeting_title": str(meeting_case.get("meeting_title") or name or "")[:512] or None,
                        "observation_type": meeting_case.get("observation_type"),
                        "meeting_type": meeting_case.get("meeting_type"),
                        "status": status if status not in ("created",) else "draft",
                        "summary": summary,
                        "state_json": json.dumps(m_state) if m_state else None,
                        "deliverable_json": json.dumps(deliverable) if deliverable is not None else None,
                    },
                )
            for table in MEETING_FK_TABLES:
                if not insp.has_table(table):
                    continue
                conn.execute(
                    text(
                        f"UPDATE {table} SET meeting_id = :mid "
                        f"WHERE project_id = :pid AND meeting_id IS NULL"
                    ),
                    {"mid": mid, "pid": pid},
                )
