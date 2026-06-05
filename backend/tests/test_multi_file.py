"""多文件跨文件比对集成测试"""
import shutil
from pathlib import Path

import pytest

from app.database import SessionLocal, init_db
from app.models import FileRecord, Project, Risk
from app.services.agent.workflow import AgentWorkflow
from app.services.seed import seed_rules

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    yield session
    session.close()


def test_multi_file_cross_check(db, tmp_path):
    if not (FIXTURES / "sample_expense.csv").exists():
        pytest.skip("fixtures not generated")

    seed_rules(db)
    p = Project(name="跨文件测试", status="created")
    db.add(p)
    db.commit()
    db.refresh(p)

    for fname in [
        "sample_expense.csv",
        "sample_invoice_list.csv",
        "sample_bank_statement.csv",
    ]:
        src = FIXTURES / fname
        if not src.exists():
            continue
        dest = tmp_path / fname
        shutil.copy(src, dest)
        db.add(
            FileRecord(
                project_id=p.id,
                file_name=fname,
                file_type="excel",
                storage_path=str(dest),
                parse_status="uploaded",
            )
        )
    db.commit()

    AgentWorkflow(db, p.id).run()
    risks = db.query(Risk).filter_by(project_id=p.id).all()

    assert len(risks) >= 5
    categories = {r.risk_category for r in risks}
    assert "税务风险" in categories or "票据风险" in categories
    assert any("重复" in r.problem or "INV" in r.problem for r in risks) or len(risks) >= 8
