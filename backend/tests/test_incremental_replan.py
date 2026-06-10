from app.models import FileRecord
from app.services.agent.incremental_replan import build_incremental_plan, diff_uploaded_files


def test_diff_detects_new_files():
    prev = {"processed_file_ids": ["f1"], "present_categories": ["expense_detail"]}
    files = [
        FileRecord(id="f1", file_name="a.csv", document_category="expense_detail"),
        FileRecord(id="f2", file_name="b.csv", document_category="bank_statement"),
    ]
    diff = diff_uploaded_files(prev, files)
    assert diff.new_file_ids == ["f2"]
    assert "bank_statement" in diff.new_categories


def test_build_incremental_plan_steps():
    base = {"focus_areas": ["资金风险"], "steps": ["parse"]}
    from app.services.agent.incremental_replan import IncrementalDiff

    diff = IncrementalDiff(new_file_ids=["f2"], new_categories={"bank_statement"})
    plan = build_incremental_plan(base, diff)
    assert plan["incremental"] is True
    assert "cross_check" in plan["steps"] or "cross_checking" in str(plan["steps"])
