from __future__ import annotations

from typing import Optional, Type, TypeVar

from sqlalchemy.orm import Query, Session

T = TypeVar("T")


def scoped_query(
    db: Session,
    model: Type[T],
    project_id: str,
    meeting_id: Optional[str] = None,
) -> Query:
    """按 project 查询；若指定 meeting_id 则严格隔离子会议数据。"""
    q = db.query(model).filter_by(project_id=project_id)
    if meeting_id is not None:
        q = q.filter_by(meeting_id=meeting_id)
    return q


def scoped_delete(
    db: Session,
    model: Type[T],
    project_id: str,
    meeting_id: Optional[str] = None,
) -> int:
    return scoped_query(db, model, project_id, meeting_id).delete(synchronize_session=False)
