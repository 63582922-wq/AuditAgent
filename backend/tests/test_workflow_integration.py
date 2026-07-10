import shutil
from pathlib import Path

import pytest

from app.database import SessionLocal, init_db
from app.models import Project, FileRecord, Meeting, Risk
from app.services.agent.workflow import AgentWorkflow
from app.services.seed import seed_rules


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    yield session
    session.close()


def test_workflow_detects_expense_risks(db, tmp_path):
    seed_rules(db)
    p = Project(name="集成测试", status="created")
    db.add(p)
    db.commit()
    db.refresh(p)

    src = Path(__file__).resolve().parents[2] / "fixtures" / "sample_expense.csv"
    dest = tmp_path / "sample_expense.csv"
    shutil.copy(src, dest)

    db.add(
        FileRecord(
            project_id=p.id,
            file_name="sample_expense.csv",
            file_type="excel",
            storage_path=str(dest),
            parse_status="uploaded",
        )
    )
    db.commit()

    AgentWorkflow(db, p.id).run()
    db.refresh(p)

    risks = db.query(Risk).filter_by(project_id=p.id).all()
    assert p.status == "completed"
    assert len(risks) >= 2
    assert any("发票" in r.problem for r in risks)


def test_compliance_workflow_runs_domain_fact_checks(db, tmp_path, monkeypatch):
    seed_rules(db)
    project = Project(name="合规主流程", status="created", state_json={"agent_domain": "compliance"})
    db.add(project)
    db.commit()
    meeting = Meeting(
        project_id=project.id,
        meeting_code="A1P260307357",
        observation_type="远程观察",
        status="ready",
        state_json={
            "agent_domain": "compliance",
            "meeting_case": {
                "meeting_code": "A1P260307357",
                "observation_type": "远程观察",
                "planned_attendees": 6,
                "planned_duration_minutes": 30,
            },
        },
    )
    db.add(meeting)
    db.commit()

    specs = [
        ("A1P260307357.pdf", "pdf", "a1_meeting_export"),
        ("Remote_A1P260307357_现场确认单.jpg", "image", "observation_confirmation"),
        ("Remote_A1P260307357_签到表.jpg", "image", "sign_in_record"),
        ("Remote_A1P260307357_PPT.jpg", "image", "presentation_material"),
        ("Remote_A1P260307357_沟通短信.jpg", "image", "coordination_sms"),
    ]
    for file_name, file_type, category in specs:
        path = tmp_path / file_name
        path.write_text("placeholder", encoding="utf-8")
        db.add(
            FileRecord(
                project_id=project.id,
                meeting_id=meeting.id,
                file_name=file_name,
                file_type=file_type,
                document_category=category,
                storage_path=str(path),
                parse_status="uploaded",
                confidence=0.95,
            )
        )
    db.commit()

    def fake_classify(file_name, ext, headers=None, text=""):
        for name, file_type, category in specs:
            if name == file_name:
                return {"file_type": file_type, "document_category": category, "confidence": 0.96}
        return {"file_type": "unknown", "document_category": "unknown", "confidence": 0.0}

    def fake_parse(self, file_record):
        if file_record.document_category == "observation_confirmation":
            fields = {
                "speaker_name": "黄洁",
                "speaker_service_minutes": 10,
                "actual_duration_minutes": 30,
                "actual_start_time": "18:00",
                "actual_end_time": "18:30",
                "vision_confidence": 0.9,
            }
            return {"file_type": "image", "text_content": "确认单 18:00-18:30 共计10分钟", "fields": fields}
        if file_record.document_category == "sign_in_record":
            return {"file_type": "image", "text_content": "辛璐 已签到\n姜越 已签到", "fields": {"vision_confidence": 0.72}}
        if file_record.document_category == "presentation_material":
            fields = {
                "presentation_topic": "宝山学术交流0506",
                "material_code": "M-CN-123456",
                "ppt_pages": 30,
                "vision_confidence": 0.88,
            }
            return {"file_type": "image", "text_content": "幻灯片 1/30", "fields": fields}
        return {"file_type": file_record.file_type, "text_content": "会议编号 A1P260307357", "fields": {}}

    monkeypatch.setattr("app.services.agent.workflow.classify_document", fake_classify)
    monkeypatch.setattr(AgentWorkflow, "_parse_file", fake_parse)
    monkeypatch.setattr(AgentWorkflow, "_generate_outputs", lambda self, project, missing: None)
    monkeypatch.setattr(
        "app.services.agent.workflow.generate_finding_narratives",
        lambda hits, profile, obs_type="远程观察": [{**hit, "analysis": hit["suggestion"]} for hit in hits],
        raising=False,
    )

    AgentWorkflow(db, project.id, meeting_id=meeting.id).run()
    db.refresh(project)
    db.refresh(meeting)

    meeting_case = meeting.state_json["meeting_case"]
    assert meeting_case["actual_sign_in_count"] == 2
    assert meeting_case["material_code"] == "M-CN-123456"
    assert meeting_case["ppt_pages"] == 30

    risks = db.query(Risk).filter_by(project_id=project.id, meeting_id=meeting.id).all()
    assert any(r.rule_triggered == "CMP-001" for r in risks)
    assert all(r.rule_triggered != "CMP-005" for r in risks)
