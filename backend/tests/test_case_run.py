import pytest

from app.models import FileRecord, Meeting, Project
from app.services.agent.case_run import (
    create_case_run,
    finish_case_run,
    mark_case_run_started,
    transition_case_run,
)


def test_case_run_snapshots_input_hash_and_enforces_lifecycle(db, tmp_path):
    project = Project(name="CaseRun 生命周期测试", status="active")
    db.add(project)
    db.commit()
    meeting = Meeting(project_id=project.id, meeting_code="RUN-001", status="draft", state_json={})
    db.add(meeting)
    db.commit()
    source = tmp_path / "确认单.jpg"
    source.write_bytes(b"evidence-snapshot")
    db.add(
        FileRecord(
            project_id=project.id,
            meeting_id=meeting.id,
            file_name=source.name,
            file_type="image",
            document_category="observation_confirmation",
            storage_path=str(source),
            parse_status="uploaded",
        )
    )
    db.commit()

    run = create_case_run(db, project.id, meeting.id)
    assert run.status == "queued"
    assert run.input_snapshot_json["files"][0]["sha256"]
    assert run.runtime_snapshot_json["prompt_version"]
    assert run.runtime_snapshot_json["rule_version"].startswith("sha256:")

    mark_case_run_started(db, run)
    finish_case_run(db, run, status="needs_review", result={"reason": "evidence_conflict"})
    assert run.status == "needs_review"
    assert run.result_json == {"reason": "evidence_conflict"}
    with pytest.raises(ValueError, match="invalid CaseRun transition"):
        transition_case_run(db, run, "running")
