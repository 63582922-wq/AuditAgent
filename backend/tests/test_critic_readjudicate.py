from app.services.agent.critic import CriticResult, validate_risk_evidence
from app.services.agent.critic_readjudicate import readjudicate_flagged_batch


def test_readjudicate_batch_empty_when_all_valid():
    risks = [
        {
            "risk_id": "R1",
            "problem": "测试",
            "analysis": "金额 5000 与证据一致。",
            "evidence_json": {"amount": 5000},
        }
    ]
    results = [validate_risk_evidence(r) for r in risks]
    out = readjudicate_flagged_batch(None, risks, results, {})
    assert out[0]["analysis"] == risks[0]["analysis"]


def test_readjudicate_batch_with_mock_llm(monkeypatch):
    risks = [
        {
            "risk_id": "R2",
            "problem": "缺发票",
            "analysis": "该笔 999999 元缺少发票。",
            "evidence_json": {"amount": 128000},
            "risk_level": "高",
        }
    ]
    critic = validate_risk_evidence(risks[0])
    assert not critic.valid

    def fake_chat_json(messages, schema_hint=None):
        return {
            "results": [
                {
                    "risk_id": "R2",
                    "analysis": "证据显示金额 128000 元，缺少对应发票支撑。",
                    "confidence": 0.92,
                    "manual_review_required": False,
                    "risk_level": "高",
                    "reasoning": "修正表述",
                }
            ]
        }

    monkeypatch.setattr("app.services.agent.llm_client.chat_json", fake_chat_json)
    monkeypatch.setattr("app.services.agent.llm_client.require_agent_llm", lambda: None)
    monkeypatch.setattr(
        "app.services.agent.critic_readjudicate.format_memories_for_prompt",
        lambda mems: "",
    )
    monkeypatch.setattr(
        "app.services.agent.critic_readjudicate.retrieve_memories",
        lambda db, **kwargs: [],
    )

    out = readjudicate_flagged_batch(None, risks, [critic], {"focus_areas": ["票据"]})
    assert "128000" in out[0]["analysis"]
    assert out[0].get("readjudicated") is True
