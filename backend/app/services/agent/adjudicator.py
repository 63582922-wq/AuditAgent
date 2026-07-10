from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.exceptions import FXPGError
from app.services.agent.llm_client import chat_json, require_agent_llm
from app.services.agent.sub_agents import pick_sub_agent_for_risk
from app.services.memory_rag import format_memories_for_prompt, retrieve_memories

ADJUDICATE_BATCH_SIZE = 5
ADJUDICATE_MAX_WORKERS = 3


def _build_adjudicate_prompt(risks: List[Dict[str, Any]], plan: Dict[str, Any], memory_text: str) -> str:
    focus = "、".join(plan.get("focus_areas") or [])
    sub_agents = plan.get("sub_agents") or []
    team = ""
    if sub_agents:
        team = "协同子 Agent：" + "、".join(
            f"{sa.get('name')}（{sa.get('station')}）" for sa in sub_agents
        ) + "\n"
    briefs = plan.get("sub_agent_briefs") or {}
    if briefs:
        brief_lines = []
        for agent_id, brief in briefs.items():
            if isinstance(brief, dict):
                brief_lines.append(
                    f"- {brief.get('title') or agent_id}: {brief.get('summary', '')}"
                    + (f" 关注点: {', '.join(brief.get('focus_risks') or [])}" if brief.get("focus_risks") else "")
                )
        if brief_lines:
            team += "子 Agent 专员简报：\n" + "\n".join(brief_lines[:5]) + "\n"
    synthesis = plan.get("synthesis_brief") or {}
    if isinstance(synthesis, dict) and synthesis.get("summary"):
        team += f"主 Agent 汇总：{synthesis['summary']}\n"
        notes = synthesis.get("priority_findings") or synthesis.get("coordination_notes")
        if notes:
            team += f"优先事项：{notes}\n"
    items = []
    sub_agents = plan.get("sub_agents") or []
    for r in risks:
        sa = pick_sub_agent_for_risk(r, sub_agents)
        items.append(
            {
                "risk_id": r.get("risk_id"),
                "problem": r.get("problem"),
                "risk_category": r.get("risk_category"),
                "risk_level": r.get("risk_level"),
                "evidence": r.get("evidence_json", {}),
                "suggestion": r.get("suggestion"),
                "sub_agent": sa.get("name") if sa else None,
            }
        )
    domain = (plan.get("agent_domain") or settings.agent_domain or "accounting").lower()
    role_prompt = (
        "你是会计风险评估 Agent，对工具层（规则/交叉比对）命中项做综合研判。"
        if domain == "accounting"
        else "你是会议合规观察（remote observation）Agent，对工具层（规则/交叉比对）命中项做综合研判。"
    )
    return (
        f"{role_prompt}\n"
        f"{team}"
        f"分析重点：{focus or '综合'}\n"
        f"相关记忆：\n{memory_text}\n"
        f"待研判风险（JSON 数组）：\n{json.dumps(items, ensure_ascii=False)}\n"
        "输出 JSON 对象，字段 results 为数组，每项含："
        "risk_id, analysis(80-150字), confidence(0-1), "
        "manual_review_required(bool), risk_level(高/中/低), reasoning(一句话)"
    )


def adjudicate_batch(
    db: Optional[Session],
    risks: List[Dict[str, Any]],
    plan: Optional[Dict[str, Any]] = None,
    memory_text: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """批量 LLM 研判（单批）。"""
    require_agent_llm()
    plan = plan or {}
    if not risks:
        return []

    if memory_text is None:
        memory_text = _memory_text_for_risks(db, risks)

    domain = plan.get("agent_domain") or settings.agent_domain
    result = chat_json(
        [{"role": "user", "content": _build_adjudicate_prompt(risks, plan, memory_text)}],
        schema_hint='{"results":[{"risk_id":"","analysis":"","confidence":0.9,"manual_review_required":false,"risk_level":"中","reasoning":""}]}',
        domain=domain,
    )
    by_id = {item.get("risk_id"): item for item in result.get("results") or []}

    out: List[Dict[str, Any]] = []
    for risk in risks:
        merged = dict(risk)
        item = by_id.get(risk.get("risk_id"))
        if not item or not item.get("analysis"):
            raise FXPGError(
                f"Agent 研判失败：{risk.get('risk_id', risk.get('problem'))}",
                code="AGENT_ADJUDICATION_FAILED",
                status=502,
            )
        merged["analysis"] = item["analysis"]
        if isinstance(item.get("confidence"), (int, float)):
            merged["confidence"] = float(item["confidence"])
        if "manual_review_required" in item:
            merged["manual_review_required"] = bool(item["manual_review_required"])
        if item.get("risk_level") in ("高", "中", "低"):
            merged["risk_level"] = item["risk_level"]
        merged["agent_reasoning"] = item.get("reasoning", "")
        out.append(merged)
    return out


def adjudicate_one(
    db: Optional[Session],
    risk: Dict[str, Any],
    plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """单条研判（兼容旧调用）。"""
    return adjudicate_batch(db, [risk], plan)[0]


def _chunk_risks(risks: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [risks[i : i + size] for i in range(0, len(risks), size)]


def _memory_text_for_risks(db: Optional[Session], risks: List[Dict[str, Any]]) -> str:
    query = " ".join(f"{r.get('risk_category')} {r.get('problem')}" for r in risks[:5])
    mems = retrieve_memories(db, query_text=query, limit=5)
    return format_memories_for_prompt(mems)


def adjudicate_risks(
    db: Optional[Session],
    risks: List[Dict[str, Any]],
    plan: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """全部风险须经 Agent LLM 研判（并行批处理）。"""
    if not risks:
        return risks
    require_agent_llm()

    sorted_risks = sorted(
        risks,
        key=lambda r: {"高": 0, "中": 1, "低": 2}.get(r.get("risk_level", "低"), 3),
    )
    memory_text = _memory_text_for_risks(db, sorted_risks)
    batches = _chunk_risks(sorted_risks, ADJUDICATE_BATCH_SIZE)
    workers = min(ADJUDICATE_MAX_WORKERS, max(1, settings.job_workers))
    adjudicated: List[Dict[str, Any]] = []

    if len(batches) == 1:
        adjudicated = adjudicate_batch(None, batches[0], plan, memory_text)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(adjudicate_batch, None, batch, plan, memory_text): batch for batch in batches}
            for future in as_completed(futures):
                adjudicated.extend(future.result())

    by_id = {r.get("risk_id"): r for r in adjudicated}
    return [by_id.get(r.get("risk_id"), r) for r in risks]
