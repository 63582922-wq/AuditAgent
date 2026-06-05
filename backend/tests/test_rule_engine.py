import pytest

from app.services.rule_engine import evaluate_condition, run_rules_on_rows


EXPENSE_RULE = {
    "rule_id": "EXP-001",
    "rule_name": "大额费用缺少发票",
    "risk_category": "税务风险",
    "risk_level": "高",
    "applicable_document_type": "expense_detail",
    "condition_json": {
        "all": [
            {"field": "amount", "operator": ">=", "value": 10000},
            {"field": "invoice_number", "operator": "is_empty"},
        ]
    },
    "evidence_fields": ["amount", "invoice_number"],
    "suggestion_template": "缺发票",
    "manual_review_required": True,
    "enabled": True,
}


def test_large_expense_without_invoice():
    rows = [
        {
            "row_number": 2,
            "values": {"金额": 128000, "发票号": ""},
            "columns_map": {"金额": "amount", "发票号": "invoice_number"},
            "sheet_name": "费用明细",
        }
    ]
    hits = run_rules_on_rows(rows, [EXPENSE_RULE], {"file_id": "f1", "document_category": "expense_detail"})
    assert len(hits) == 1
    assert hits[0]["rule"]["rule_id"] == "EXP-001"


def test_small_expense_not_triggered():
    rows = [
        {
            "row_number": 2,
            "values": {"金额": 100, "发票号": ""},
            "columns_map": {"金额": "amount", "发票号": "invoice_number"},
            "sheet_name": "费用明细",
        }
    ]
    hits = run_rules_on_rows(rows, [EXPENSE_RULE], {"file_id": "f1", "document_category": "expense_detail"})
    assert len(hits) == 0


def test_contains_operator():
    row = {"summary": "业务招待费", "amount": 8000}
    cond = {"all": [{"field": "summary", "operator": "contains", "value": "招待"}]}
    assert evaluate_condition(row, cond) is True


def test_disabled_rule_skipped():
    disabled = {**EXPENSE_RULE, "enabled": False}
    rows = [
        {
            "row_number": 2,
            "values": {"金额": 128000, "发票号": ""},
            "columns_map": {"金额": "amount", "发票号": "invoice_number"},
            "sheet_name": "费用明细",
        }
    ]
    hits = run_rules_on_rows(rows, [disabled], {"file_id": "f1", "document_category": "expense_detail"})
    assert len(hits) == 0
