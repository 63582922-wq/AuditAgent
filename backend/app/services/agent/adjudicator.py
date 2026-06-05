from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.exceptions import FXPGError
from app.services.agent.llm_client import chat_json, require_agent_llm
from app.services.memory_rag import format_memories_for_prompt, retrieve_memories


def adjudicate_one(
    db: Optional[Session],
    risk: Dict[str, Any],
    plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Agent 对单条风险做 LLM 综合研判。"""
    require_agent_llm()
    out = dict(risk)
    plan = plan or {}

    query = f"{risk.get('risk_category')} {risk.get('problem')}"
    mems = retrieve_memories(
        db,
        risk_category=risk.get("risk_category"),
        query_text=query,
        limit=5,
    )
    memory_text = format_memories_for_prompt(mems)
    focus = "、".join(plan.get("focus_areas") or [])

    result = chat_json(
        [
            {
                "role": "user",
                "content": (
                    f"你是会计风险评估 Agent，对工具层（规则/交叉比对）命中项做综合研判。\n"
                    f"分析重点：{focus or '综合'}\n"
                    f"问题：{risk.get('problem')}\n"
                    f"类别：{risk.get('risk_category')} / 等级：{risk.get('risk_level')}\n"
                    f"证据：{json.dumps(risk.get('evidence_json', {}), ensure_ascii=False)}\n"
                    f"规则建议：{risk.get('suggestion')}\n"
                    f"相关记忆：\n{memory_text}\n"
                    "输出 JSON：analysis(80-150字), confidence(0-1), "
                    "manual_review_required(bool), risk_level(高/中/低), reasoning(一句话)"
                ),
            }
        ],
        schema_hint='{"analysis":"","confidence":0.9,"manual_review_required":false,"risk_level":"中","reasoning":""}',
    )

    if not result.get("analysis"):
        raise FXPGError(
            f"Agent 研判失败：{risk.get('risk_id', risk.get('problem'))}",
            code="AGENT_ADJUDICATION_FAILED",
            status=502,
        )

    out["analysis"] = result["analysis"]
    if isinstance(result.get("confidence"), (int, float)):
        out["confidence"] = float(result["confidence"])
    if "manual_review_required" in result:
        out["manual_review_required"] = bool(result["manual_review_required"])
    if result.get("risk_level") in ("高", "中", "低"):
        out["risk_level"] = result["risk_level"]
    out["agent_reasoning"] = result.get("reasoning", "")
    return out


def adjudicate_risks(
    db: Optional[Session],
    risks: List[Dict[str, Any]],
    plan: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """全部风险须经 Agent LLM 研判。"""
    if not risks:
        return risks
    require_agent_llm()

    sorted_risks = sorted(
        risks,
        key=lambda r: {"高": 0, "中": 1, "低": 2}.get(r.get("risk_level", "低"), 3),
    )
    adjudicated = [adjudicate_one(db, risk, plan) for risk in sorted_risks]
    by_id = {r.get("risk_id"): r for r in adjudicated}
    return [by_id.get(r.get("risk_id"), r) for r in risks]
