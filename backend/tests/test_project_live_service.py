from app.models import FileRecord, Meeting, Project
from app.services.project_live_service import build_meeting_live, compact_live_state


def test_compact_live_state_preserves_material_facts_for_frontend_and_agent():
    state = {
        "agent_domain": "compliance",
        "present_categories": ["a1_meeting_export", "sign_in_record"],
        "category_counts": {"a1_meeting_export": 1, "sign_in_record": 3},
        "missing_documents": [],
        "large_unused_blob": {"raw": "x" * 20},
    }

    compact = compact_live_state(state)

    assert compact["present_categories"] == ["a1_meeting_export", "sign_in_record"]
    assert compact["category_counts"] == {"a1_meeting_export": 1, "sign_in_record": 3}
    assert compact["missing_documents"] == []
    assert "large_unused_blob" not in compact


def test_build_meeting_live_derives_category_counts_from_files(db):
    project = Project(name="Live facts", status="completed")
    db.add(project)
    db.commit()

    meeting = Meeting(
        project_id=project.id,
        meeting_code="A1P260307357",
        status="completed",
        state_json={
            "agent_domain": "compliance",
            "present_categories": ["a1_meeting_export", "sign_in_record"],
            "missing_documents": [],
        },
    )
    db.add(meeting)
    db.commit()

    for name, category in [
        ("A1P260307357.pdf", "a1_meeting_export"),
        ("签到表1.jpg", "sign_in_record"),
        ("签到表2.jpg", "sign_in_record"),
    ]:
        db.add(
            FileRecord(
                project_id=project.id,
                meeting_id=meeting.id,
                file_name=name,
                file_type="image" if name.endswith(".jpg") else "pdf",
                document_category=category,
                storage_path=f"/tmp/{name}",
                parse_status="done",
            )
        )
    db.commit()

    live = build_meeting_live(db, project.id, meeting.id)

    assert live.state_json["category_counts"] == {
        "a1_meeting_export": 1,
        "sign_in_record": 2,
    }
