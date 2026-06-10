from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.agent.critic import CriticResult
from app.services.agent.llm_client import chat_json, require_agent_llm


def llm_critic_review(risk: Dict[str, Any], rule_result: CriticResult) -> CriticResult:
    """对规则 Critic 标记的疑点做 LLM 二轮校验。"""
    if not settings.enable_critic_llm:
        return rule_result
    if rule_result.valid:
        return rule_result

    require_agent_llm()
    rid = str(risk.get("risk_id") or "")
    prompt = (
        "你是会计审计 Critic，复核 Agent 研判是否忠实于证据。\n"
        f"问题：{risk.get('problem')}\n"
        f"研判：{risk.get('analysis')}\n"
        f"证据 JSON：{json.dumps(risk.get('evidence_json', {}), ensure_ascii=False)}\n"
        f"规则 Critic 意见：{rule_result.message}\n"
        "输出 JSON：valid(bool), confidence(0-1), message(一句话), "
        "manual_review_required(bool)。valid=true 表示研判可接受。"
    )
    try:
        result = chat_json(
            [{"role": "user", "content": prompt}],
            schema_hint='{"valid":false,"confidence":0.5,"message":"","manual_review_required":true}',
        )
        valid = bool(result.get("valid"))
        return CriticResult(
            risk_id=rid,
            valid=valid,
            flags=[] if valid else rule_result.flags + ["llm_critic_reject"],
            score=float(result.get("confidence") or (0.85 if valid else 0.4)),
            message=str(result.get("message") or rule_result.message),
        )
    except Exception:
        return rule_result


def llm_critic_review_batch(
    risks: List[Dict[str, Any]],
    rule_results: List[CriticResult],
) -> List[CriticResult]:
    by_id = {r.risk_id: r for r in rule_results}
    out: List[CriticResult] = []
    for risk in risks:
        rid = str(risk.get("risk_id") or "")
        base = by_id.get(rid) or CriticResult(risk_id=rid, valid=True)
        if base.valid:
            out.append(base)
        else:
            out.append(llm_critic_review(risk, base))
    return out
