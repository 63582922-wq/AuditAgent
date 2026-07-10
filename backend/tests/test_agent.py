import pytest
import threading

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


def test_adjudicate_risks_reads_memory_before_parallel_batches(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "job_workers", 3)
    monkeypatch.setattr("app.services.agent.adjudicator.require_agent_llm", lambda: None)

    memory_threads = []

    def fake_retrieve_memories(db, **kwargs):
        memory_threads.append(threading.current_thread().name)
        if threading.current_thread() is not threading.main_thread():
            raise AssertionError("SQLAlchemy session should not be read from adjudication worker threads")
        return []

    def fake_chat_json(messages, schema_hint="", domain=None):
        import re

        prompt = messages[-1]["content"]
        ids = re.findall(r'"risk_id"\s*:\s*"([^"]+)"', prompt)
        return {
            "results": [
                {
                    "risk_id": rid,
                    "analysis": f"Agent 已复核 {rid} 的证据链。",
                    "confidence": 0.9,
                    "manual_review_required": False,
                    "risk_level": "中",
                    "reasoning": "批量复核",
                }
                for rid in ids
            ]
        }

    monkeypatch.setattr("app.services.agent.adjudicator.retrieve_memories", fake_retrieve_memories)
    monkeypatch.setattr("app.services.agent.adjudicator.format_memories_for_prompt", lambda mems: "")
    monkeypatch.setattr("app.services.agent.adjudicator.chat_json", fake_chat_json)

    risks = [
        {
            "risk_id": f"R-{idx}",
            "risk_category": "税务风险",
            "risk_level": "中",
            "problem": "测试风险",
            "suggestion": "复核",
            "evidence_json": {"idx": idx},
            "confidence": 0.9,
        }
        for idx in range(7)
    ]

    out = adjudicate_risks(object(), risks, {"focus_areas": ["税务风险"]})

    assert len(out) == 7
    assert memory_threads == [threading.main_thread().name]
