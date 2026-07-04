from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import ParsedDocument


def upsert_parsed_document(
    db: Session,
    *,
    project_id: str,
    meeting_id: str | None,
    file_id: str,
    document_type: str,
    content_json: dict[str, Any],
    text_content: str = "",
) -> ParsedDocument:
    """Upsert ParsedDocument by the unique file_id, preserving meeting scope."""
    doc = db.query(ParsedDocument).filter_by(file_id=file_id).one_or_none()
    if doc is None:
        doc = ParsedDocument(
            project_id=project_id,
            meeting_id=meeting_id,
            file_id=file_id,
            document_type=document_type,
            content_json=content_json,
            text_content=text_content,
        )
        db.add(doc)
        return doc

    doc.project_id = project_id
    doc.meeting_id = meeting_id
    doc.document_type = document_type
    doc.content_json = content_json
    doc.text_content = text_content
    return doc
