import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def db():
    from app.database import SessionLocal, init_db

    init_db()
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def mock_agent_llm(monkeypatch):
    """测试环境模拟 LLM，满足纯智能体模式要求。"""
    from app.config import settings
    from app.services.embedding_service import _local_embed

    monkeypatch.setattr(settings, "llm_api_key", "test-key-for-pytest")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "vision_api_key", "")
    monkeypatch.setattr(settings, "enable_llm", True)
    monkeypatch.setattr(settings, "human_gate_manual_threshold", 999)
    monkeypatch.setattr(settings, "human_gate_high_threshold", 999)
    monkeypatch.setattr(settings, "human_gate_critic_threshold", 999)
    monkeypatch.setattr(settings, "enable_critic_llm", False)
    monkeypatch.setattr(settings, "agent_execution_mode", "pipeline")
    monkeypatch.setattr(settings, "enable_sub_agent_llm", False)
    monkeypatch.setattr(settings, "mcp_servers", "[]")
    monkeypatch.setattr(
        "app.services.embedding_service.embed_text",
        lambda text: _local_embed(text),
    )

    plan_json = json.dumps(
        {
            "steps": ["parse", "extract", "run_rules", "cross_check", "adjudicate", "report"],
            "focus_areas": ["税务风险", "票据风险"],
            "missing_documents": ["tax_return"],
            "priority_actions": ["扫描费用与发票", "交叉比对金额"],
            "reasoning": "测试 Agent 计划",
            "sub_agents": [
                {"id": "tax", "name": "税务专员", "station": "税务席", "agent_say": "测试", "score": 10}
            ],
            "agent_mode": "agent",
        },
        ensure_ascii=False,
    )
    adjudicate_json = json.dumps(
        {
            "analysis": "Agent 测试研判：该风险需结合凭证与合同进一步核实。",
            "confidence": 0.88,
            "manual_review_required": True,
            "risk_level": "高",
            "reasoning": "mock",
        },
        ensure_ascii=False,
    )
    adjudicate_batch_json = json.dumps(
        {
            "results": [
                {
                    "risk_id": "EXP-001-2",
                    "analysis": "Agent 测试研判：该风险需结合凭证与合同进一步核实。",
                    "confidence": 0.88,
                    "manual_review_required": True,
                    "risk_level": "高",
                    "reasoning": "mock",
                }
            ]
        },
        ensure_ascii=False,
    )

    call_n = {"plan": 0}

    def fake_chat_completion(messages, tools=None, tool_choice=None, temperature=0.2):
        if tools and call_n["plan"] == 0:
            call_n["plan"] += 1
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_test_1",
                        "type": "function",
                        "function": {"name": "list_uploaded_files", "arguments": "{}"},
                    }
                ],
            }
        last = messages[-1]["content"] if messages else ""
        if "综合研判" in last:
            return {"role": "assistant", "content": adjudicate_batch_json}
        return {"role": "assistant", "content": plan_json}

    def fake_chat_json(messages, schema_hint=""):
        last = messages[-1]["content"] if messages else ""
        if "综合研判" in last or "待研判风险" in last:
            data = json.loads(adjudicate_batch_json)
            if "results" in data and data["results"]:
                first = data["results"][0]
                import re

                ids = re.findall(r'"risk_id"\s*:\s*"([^"]+)"', last)
                if ids:
                    data["results"] = [
                        {**first, "risk_id": rid} for rid in ids
                    ]
            return data
        return json.loads(plan_json)

    monkeypatch.setattr("app.services.agent.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr("app.services.agent.llm_client.chat_json", fake_chat_json)
    monkeypatch.setattr("app.services.agent.planner.chat_completion", fake_chat_completion)
    monkeypatch.setattr("app.services.agent.planner.chat_json", fake_chat_json)
    monkeypatch.setattr("app.services.agent.adjudicator.chat_json", fake_chat_json)
