import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.main import app
from app.models import AgentActionProposal, AnalysisJob, FileRecord, LearningProposal, Project, Risk
from app.services.agent.workflow import AgentWorkflow
from app.services.meeting_service import create_meeting
from app.services.seed import seed_rules


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client():
    return TestClient(app)


def test_stats_endpoint(client, db):
    seed_rules(db)
    res = client.get("/api/stats")
    assert res.status_code == 200
    data = res.json()
    assert "project_count" in data
    assert data["rule_count"] >= 50


def test_dismissed_risks_excluded_from_outputs(db, tmp_path):
    seed_rules(db)
    p = Project(name="复核过滤测试", status="created")
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

    wf = AgentWorkflow(db, p.id)
    wf.run()
    risks = db.query(Risk).filter_by(project_id=p.id).all()
    assert len(risks) >= 1

    risks[0].status = "dismissed"
    db.commit()

    wf.regenerate_outputs_only()
    active = db.query(Risk).filter_by(project_id=p.id).filter(Risk.status != "dismissed").count()
    assert active == len(risks) - 1


def test_batch_delete_project_removes_new_project_child_tables(client, db):
    project = Project(name="删除级联测试", status="active")
    db.add(project)
    db.commit()
    db.refresh(project)
    meeting = create_meeting(db, project.id, meeting_code="DEL001")
    proposal = AgentActionProposal(
        project_id=project.id,
        meeting_id=meeting.id,
        action_id="test-action",
        label="测试动作",
        description="测试删除级联",
        segment="files",
    )
    db.add(proposal)
    db.commit()
    project_id = project.id
    proposal_id = proposal.id

    res = client.post("/api/projects/batch-delete", json={"project_ids": [project_id]})

    assert res.status_code == 200
    assert res.json()["deleted"] == 1
    db.expire_all()
    assert db.get(Project, project_id) is None
    assert db.get(AgentActionProposal, proposal_id) is None


def test_agent_feedback_is_governed_and_meeting_job_can_be_cancelled(client, db):
    project = Project(name="受控学习与取消测试", status="active")
    db.add(project)
    db.commit()
    meeting = create_meeting(db, project.id, meeting_code="GOVERNED-001")
    job = AnalysisJob(
        project_id=project.id,
        meeting_id=meeting.id,
        status="queued",
        current_step="queued",
        progress_pct=0,
    )
    db.add(job)
    db.commit()

    feedback = client.post(
        "/api/agent/feedback",
        json={
            "project_id": project.id,
            "meeting_id": meeting.id,
            "feedback": "确认单里的实际参会人数应以平台峰值为准。",
            "original_conclusion": "当前人数为 12",
        },
    )
    assert feedback.status_code == 200
    assert feedback.json()["status"] == "pending"
    assert db.query(LearningProposal).filter_by(project_id=project.id, meeting_id=meeting.id).count() == 1

    cancelled = client.post(f"/api/projects/{project.id}/meetings/{meeting.id}/jobs/{job.id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancel_requested"
    db.refresh(job)
    assert job.status == "cancel_requested"
