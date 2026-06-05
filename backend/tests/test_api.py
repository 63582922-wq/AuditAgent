import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.main import app
from app.models import FileRecord, Project, Risk
from app.services.agent.workflow import AgentWorkflow
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
