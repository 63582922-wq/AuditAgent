from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Risk
from app.services.agent.agent_trace import AgentTrace
from app.services.agent.critic import CriticResult, apply_critic_to_risks, validate_risks
from app.services.agent.critic_llm import llm_critic_review_batch
from app.services.agent.workflow import AgentWorkflow
from app.services.memory_rag import format_memories_for_prompt, retrieve_memories


@dataclass
class CriticLoopResult:
    validated: int = 0
    flagged: int = 0
    readjudicate_rounds: int = 0
    outputs_regenerated: bool = False
    critic_results: List[CriticResult] = field(default_factory=list)


def _build_readjudicate_prompt(
    risks: List[Dict[str, Any]],
    plan: Dict[str, Any],
    memory_text: str,
    critic_by_id: Dict[str, CriticResult],
) -> str:
    focus = "、".join(plan.get("focus_areas") or [])
    items = []
    for r in risks:
        rid = str(r.get("risk_id") or "")
        critic = critic_by_id.get(rid)
        items.append(
            {
                "risk_id": rid,
                "problem": r.get("problem"),
                "risk_category": r.get("risk_category"),
                "risk_level": r.get("risk_level"),
                "evidence": r.get("evidence_json", {}),
                "previous_analysis": r.get("analysis"),
                "critic_feedback": critic.message if critic else "",
                "critic_flags": critic.flags if critic else [],
            }
        )
    return (
        "你是会计风险评估 Agent。上一轮研判未通过 Critic 证据链校验，请根据 Critic 意见修正研判。\n"
        "要求：analysis 中的数值必须能在 evidence 中找到；不要编造未出现的金额。\n"
        f"分析重点：{focus or '综合'}\n"
        f"相关记忆：\n{memory_text}\n"
        f"待修正风险：\n{json.dumps(items, ensure_ascii=False)}\n"
        "输出 JSON 对象 results 数组，每项含："
        "risk_id, analysis(80-150字), confidence(0-1), "
        "manual_review_required(false), risk_level(高/中/低), reasoning(一句话)"
    )


def readjudicate_flagged_batch(
    db: Session,
    risks: List[Dict[str, Any]],
    critic_results: List[CriticResult],
    plan: Dict[str, Any],
) -> List[Dict[str, Any]]:
    critic_by_id = {c.risk_id: c for c in critic_results if not c.valid}
    flagged = [r for r in risks if str(r.get("risk_id") or "") in critic_by_id]
    if not flagged:
        return risks

    query = " ".join(f"{r.get('risk_category')} {r.get('problem')}" for r in flagged[:3])
    mems = retrieve_memories(db, query_text=query, limit=5)
    memory_text = format_memories_for_prompt(mems)

    from app.services.agent.llm_client import chat_json, require_agent_llm

    require_agent_llm()
    result = chat_json(
        [{"role": "user", "content": _build_readjudicate_prompt(flagged, plan, memory_text, critic_by_id)}],
        schema_hint='{"results":[{"risk_id":"","analysis":"","confidence":0.9,"manual_review_required":false,"risk_level":"中","reasoning":""}]}',
    )
    by_id = {item.get("risk_id"): item for item in result.get("results") or []}

    merged_by_id = {str(r.get("risk_id") or ""): dict(r) for r in risks}
    for rid, item in by_id.items():
        if not item or not item.get("analysis"):
            continue
        base = merged_by_id.get(rid)
        if not base:
            continue
        base["analysis"] = item["analysis"]
        if isinstance(item.get("confidence"), (int, float)):
            base["confidence"] = float(item["confidence"])
        base["manual_review_required"] = False
        if item.get("risk_level") in ("高", "中", "低"):
            base["risk_level"] = item["risk_level"]
        base["agent_reasoning"] = item.get("reasoning", "")
        base["readjudicated"] = True
        merged_by_id[rid] = base
    return list(merged_by_id.values())


def _risk_to_dict(r: Risk) -> Dict[str, Any]:
    return {
        "risk_id": r.risk_id,
        "risk_category": r.risk_category,
        "risk_level": r.risk_level,
        "problem": r.problem,
        "analysis": r.analysis,
        "evidence_json": r.evidence_json,
        "suggestion": r.suggestion,
        "confidence": r.confidence,
        "manual_review_required": r.manual_review_required,
    }


def _persist_risk_updates(db: Session, risk_objects: List[Risk], risk_dicts: List[Dict[str, Any]]) -> None:
    by_id = {str(d.get("risk_id") or ""): d for d in risk_dicts}
    for obj in risk_objects:
        patch = by_id.get(obj.risk_id)
        if not patch:
            continue
        if patch.get("analysis"):
            obj.analysis = patch["analysis"]
        if patch.get("confidence") is not None:
            obj.confidence = float(patch["confidence"])
        if patch.get("risk_level"):
            obj.risk_level = patch["risk_level"]
        obj.manual_review_required = bool(patch.get("manual_review_required", False))
    db.commit()


def run_critic_readjudicate_loop(
    db: Session,
    project_id: str,
    trace: AgentTrace,
    plan: Dict[str, Any],
) -> CriticLoopResult:
    """Critic 校验 → 疑点自动重研判 → 必要时再生交付物。"""
    risk_objects = (
        db.query(Risk)
        .filter_by(project_id=project_id)
        .filter(Risk.status != "dismissed")
        .all()
    )
    if not risk_objects:
        return CriticLoopResult()

    risk_dicts = [_risk_to_dict(r) for r in risk_objects]
    readjudicate_rounds = 0
    critic_results: List[CriticResult] = []

    max_rounds = settings.critic_readjudicate_max_rounds if settings.enable_critic_readjudicate else 0

    for round_idx in range(max_rounds + 1):
        critic_results = validate_risks(risk_dicts)
        rule_flagged = [c for c in critic_results if not c.valid]
        if settings.enable_critic_llm and rule_flagged:
            critic_results = llm_critic_review_batch(risk_dicts, critic_results)

        flagged = [c for c in critic_results if not c.valid]
        if not flagged:
            break

        if round_idx >= max_rounds or not settings.enable_critic_readjudicate:
            break

        trace.log(
            "critic",
            "running",
            kind="critic",
            message=f"第 {round_idx + 1} 轮 Critic 重研判（{len(flagged)} 条疑点）",
            detail={"round": round_idx + 1, "flagged": len(flagged)},
        )
        risk_dicts = readjudicate_flagged_batch(db, risk_dicts, critic_results, plan)
        _persist_risk_updates(db, risk_objects, risk_dicts)
        readjudicate_rounds += 1

    outputs_regenerated = False
    if readjudicate_rounds > 0:
        AgentWorkflow(db, project_id).regenerate_outputs_only()
        outputs_regenerated = True
        trace.log(
            "critic",
            "completed",
            kind="critic",
            message=f"重研判 {readjudicate_rounds} 轮，交付物已更新",
            detail={"rounds": readjudicate_rounds},
        )

    flagged_final = [c for c in critic_results if not c.valid]
    orchestrator_mode = settings.agent_execution_mode == "orchestrator"
    updated = apply_critic_to_risks(risk_dicts, critic_results)

    critic_flag_count = 0
    for risk_obj, rd in zip(risk_objects, updated):
        if rd.get("critic_flags"):
            critic_flag_count += 1
            if orchestrator_mode and settings.enable_critic_readjudicate:
                risk_obj.manual_review_required = False
            else:
                risk_obj.manual_review_required = bool(rd.get("manual_review_required", True))
            if rd.get("confidence") is not None:
                risk_obj.confidence = float(rd["confidence"])
        elif orchestrator_mode:
            risk_obj.manual_review_required = False
    db.commit()

    return CriticLoopResult(
        validated=len(critic_results),
        flagged=len(flagged_final),
        readjudicate_rounds=readjudicate_rounds,
        outputs_regenerated=outputs_regenerated,
        critic_results=critic_results,
    )
