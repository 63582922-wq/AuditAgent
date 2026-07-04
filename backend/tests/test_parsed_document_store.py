from __future__ import annotations

from app.models import FileRecord, Meeting, ParsedDocument, Project
from app.services.parsed_document_store import upsert_parsed_document


def test_upsert_parsed_document_updates_existing_file_scope(db) -> None:
    project = Project(name="Parsed upsert test", status="created")
    db.add(project)
    db.commit()

    meeting = Meeting(
        project_id=project.id,
        meeting_code="SMS-UPsert",
        observation_type="远程观察",
        status="draft",
    )
    db.add(meeting)
    db.commit()

    file_record = FileRecord(
        project_id=project.id,
        meeting_id=meeting.id,
        file_name="watch.xlsx",
        file_type="excel",
        document_category="sign_in_record",
        storage_path="/tmp/watch.xlsx",
        parse_status="uploaded",
    )
    db.add(file_record)
    db.commit()

    stale = ParsedDocument(
        project_id=project.id,
        meeting_id=None,
        file_id=file_record.id,
        document_type="unknown",
        content_json={"old": True},
        text_content="old",
    )
    db.add(stale)
    db.commit()

    doc = upsert_parsed_document(
        db,
        project_id=project.id,
        meeting_id=meeting.id,
        file_id=file_record.id,
        document_type="sign_in_record",
        content_json={"new": True},
        text_content="new",
    )
    db.commit()

    rows = db.query(ParsedDocument).filter_by(file_id=file_record.id).all()
    assert len(rows) == 1
    assert doc.id == stale.id
    assert rows[0].meeting_id == meeting.id
    assert rows[0].document_type == "sign_in_record"
    assert rows[0].content_json == {"new": True}
    assert rows[0].text_content == "new"
