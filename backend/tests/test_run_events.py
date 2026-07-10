from app.models import AgentRunLog, Project
from app.services.agent.run_events import build_run_events_snapshot
from app.services.meeting_service import create_meeting


def test_terminal_meeting_marks_legacy_open_trace_events_as_inferred_completed(db):
    project = Project(name="运行追溯状态测试", status="active")
    db.add(project)
    db.commit()
    meeting = create_meeting(db, project.id, meeting_code="TRACE-001")
    meeting.status = "completed"
    db.add(
        AgentRunLog(
            project_id=project.id,
            meeting_id=meeting.id,
            step="legacy_trace",
            status="running",
            detail_json={"kind": "tool", "message": "旧运行事件"},
        )
    )
    db.commit()

    snapshot = build_run_events_snapshot(
        db,
        project_id=project.id,
        meeting_id=meeting.id,
        run=None,
    )

    assert snapshot["summary"]["running_event_count"] == 0
    assert snapshot["health"]["level"] == "healthy"
    assert snapshot["events"][0]["status"] == "completed_inferred"
    assert snapshot["events"][0]["detail"]["raw_status"] == "running"
