import pytest

from app.exceptions import FXPGError
from app.models import FileRecord
from app.services.agent.adjudicator import adjudicate_risks
from app.services.agent.llm_client import require_agent_llm
from app.services.agent.planner import plan_analysis


def test_require_agent_llm_blocks_without_key(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    with pytest.raises(FXPGError) as exc:
        require_agent_llm()
    assert exc.value.code == "AGENT_LLM_REQUIRED"


def test_plan_analysis_returns_agent_mode(db):
    files = [
        FileRecord(file_name="a.csv", document_category="expense_detail", confidence=0.9),
    ]
    plan = plan_analysis(db, "proj-1", files)
    assert plan["agent_mode"] == "agent"
    assert plan["focus_areas"]


def test_adjudicate_risks_with_agent(db):
    risks = [
        {
            "risk_id": "EXP-001-2",
            "risk_category": "税务风险",
            "risk_level": "高",
            "problem": "大额费用缺少发票",
            "suggestion": "请补充发票",
            "evidence_json": {"amount": 128000},
            "confidence": 0.9,
        }
    ]
    out = adjudicate_risks(db, risks, {"focus_areas": ["税务风险"]})
    assert out[0]["analysis"]
    assert "Agent" in out[0]["analysis"] or "核实" in out[0]["analysis"]
