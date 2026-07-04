from __future__ import annotations

from app.models import FileRecord, Meeting, Project
from app.services.meeting_service import list_meetings


def test_list_meetings_hides_empty_default_when_real_meeting_exists(db) -> None:
    project = Project(name="Project with default shell", status="active")
    db.add(project)
    db.commit()

    default = Meeting(
        project_id=project.id,
        meeting_code="DEFAULT",
        status="active",
    )
    real = Meeting(
        project_id=project.id,
        meeting_code="SMS202606090070",
        status="completed",
    )
    db.add_all([default, real])
    db.commit()

    db.add(
        FileRecord(
            project_id=project.id,
            meeting_id=real.id,
            file_name="Remote_SMS202606090070_20260615_线上直播观看数据.xlsx",
            file_type="excel",
            document_category="sign_in_record",
            storage_path="/tmp/watch.xlsx",
            parse_status="done",
        )
    )
    db.commit()

    meetings = list_meetings(db, project.id)

    assert [m.meeting_code for m in meetings] == ["SMS202606090070"]
