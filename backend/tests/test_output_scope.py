from __future__ import annotations

from app.models import Meeting, Output, Project
from app.services.agent.workflow import AgentWorkflow
from app.services.output_scope import primary_outputs


def test_primary_outputs_only_returns_formal_deliverables(db) -> None:
    project = Project(name="Project outputs", status="completed")
    db.add(project)
    db.commit()

    meeting = Meeting(project_id=project.id, meeting_code="SMS202606090070", status="completed")
    db.add(meeting)
    db.commit()

    rows = [
        ("fixed_template_excel", "固定模板输出.xlsx"),
        ("fixed_template_field_evidence", "固定模板字段证据.xlsx"),
        ("fixed_template_quality", "固定模板质量门禁.xlsx"),
        ("fixed_template_quality_json", "固定模板质量门禁.json"),
        ("finding_pdf", "Remote_Observation_Report.pdf"),
        ("deliverable_package", "SMS202606090070_RemoteObservation_20260629.zip"),
    ]
    for output_type, file_name in rows:
        db.add(
            Output(
                project_id=project.id,
                meeting_id=meeting.id,
                output_type=output_type,
                storage_path=f"/tmp/{file_name}",
                file_name=file_name,
            )
        )
    db.commit()

    outputs = primary_outputs(db, project_id=project.id, meeting_id=meeting.id)

    assert [o.output_type for o in outputs] == ["fixed_template_excel", "deliverable_package"]


def test_compliance_workflow_persists_only_primary_outputs(db, tmp_path, monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "storage_path", tmp_path)

    project = Project(name="Compliance outputs", status="completed")
    db.add(project)
    db.commit()

    meeting_case = {
        "meeting_code": "A1PPRIMARY001",
        "meeting_title": "输出收敛测试",
        "observation_type": "远程观察",
        "planned_attendees": 6,
        "actual_sign_in_count": 6,
    }
    meeting = Meeting(
        project_id=project.id,
        meeting_code="A1PPRIMARY001",
        status="completed",
        state_json={
            "agent_domain": "compliance",
            "meeting_case": meeting_case,
            "present_categories": [
                "a1_meeting_export",
                "coordination_sms",
                "meeting_agenda",
                "meeting_screenshot",
                "observation_confirmation",
                "presentation_material",
                "sign_in_record",
                "speaker_profile",
            ],
        },
    )
    db.add(meeting)
    db.commit()

    AgentWorkflow(db, project.id, meeting_id=meeting.id)._generate_outputs(project, [])

    outputs = db.query(Output).filter_by(project_id=project.id, meeting_id=meeting.id).all()

    assert [o.output_type for o in sorted(outputs, key=lambda item: item.created_at)] == [
        "fixed_template_excel",
        "deliverable_package",
    ]
