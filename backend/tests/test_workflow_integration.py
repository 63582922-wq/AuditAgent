import shutil
from pathlib import Path

import pytest

from app.database import SessionLocal, init_db
from app.models import Project, FileRecord, Risk
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
