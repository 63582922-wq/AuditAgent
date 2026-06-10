from app.services.agent.mission_planner import MissionTask
from app.services.agent.sub_agent_loop import _default_brief, _summarize_brief


def test_default_brief():
    task = MissionTask(
        id="rules",
        title="规则扫描",
        assignee="tax",
        assignee_name="税务专员",
        pipeline_steps=["running_rules"],
        objective="扫描税务规则",
    )
    brief = _default_brief(task, [{"step": "running_rules", "rule_hits": 3}])
    assert brief["agent_id"] == "tax"
    assert "税务专员" in brief["summary"]


def test_summarize_brief_mock(monkeypatch):
    task = MissionTask(
        id="cross",
        title="交叉比对",
        assignee="treasury",
        assignee_name="资金专员",
        pipeline_steps=["cross_checking"],
        objective="流水勾稽",
    )

    def fake_chat_json(messages, schema_hint=""):
        return {
            "summary": "发现 2 处流水与账面不一致",
            "findings": ["银行流水缺口"],
            "focus_risks": ["异常交易风险"],
            "confidence": 0.9,
            "tools_used": ["inspect_agent_domain"],
        }

    monkeypatch.setattr("app.services.agent.sub_agent_loop.chat_json", fake_chat_json)
    brief = _summarize_brief(task, "资金 Skill", ["inspect_agent_domain"], [{"total_risks": 2}], "调查记录")
    assert brief["summary"]
    assert brief["agent_id"] == "treasury"
