"""五文件完整端到端集成测试"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.database import SessionLocal, init_db
from app.models import FileRecord, Output, Project, Risk
from app.services.agent.workflow import AgentWorkflow
from app.services.seed import seed_rules

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
ALL_FILES = [
    "sample_expense.csv",
    "sample_invoice_list.csv",
    "sample_bank_statement.csv",
    "sample_contract.docx",
    "sample_trial_balance.xlsx",
]


@pytest.fixture(scope="module", autouse=True)
def ensure_fixtures():
    missing = [f for f in ALL_FILES if not (FIXTURES / f).exists()]
    if missing:
        script = Path(__file__).resolve().parents[2] / "scripts" / "create_fixtures.py"
        subprocess.run([sys.executable, str(script)], check=True)


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    yield session
    session.close()


def test_e2e_all_fixtures(db, tmp_path):
    seed_rules(db)
    p = Project(name="E2E 全量测试", status="created")
    db.add(p)
    db.commit()
    db.refresh(p)

    for fname in ALL_FILES:
        src = FIXTURES / fname
        assert src.exists(), f"缺少样例 {fname}"
        dest = tmp_path / fname
        shutil.copy(src, dest)
        db.add(
            FileRecord(
                project_id=p.id,
                file_name=fname,
                file_type="unknown",
                storage_path=str(dest),
                parse_status="uploaded",
            )
        )
    db.commit()

    AgentWorkflow(db, p.id).run()
    db.refresh(p)

    risks = db.query(Risk).filter_by(project_id=p.id).all()
    outputs = db.query(Output).filter_by(project_id=p.id).all()
    problems = " ".join(r.problem for r in risks)

    assert p.status == "completed"
    assert len(risks) >= 10, f"风险过少: {len(risks)}"
    assert len(outputs) >= 3, f"交付物过少: {len(outputs)}"

    assert "发票" in problems or "重复" in problems, "应检测到票据风险"
    assert "账户" in problems or "私" in problems or "银行" in problems, "应检测到银行流水风险"
    assert "合同" in problems or "金额" in problems or "一致" in problems, "应检测到交叉比对风险"
    assert any(r.risk_level == "高" for r in risks), "应存在高风险项"

    categories = {r.risk_category for r in risks}
    assert len(categories) >= 3, f"风险类别过少: {categories}"

    rule_ids = {r.rule_triggered for r in risks if r.rule_triggered}
    assert len(rule_ids) >= 4, f"触发规则过少: {rule_ids}"
