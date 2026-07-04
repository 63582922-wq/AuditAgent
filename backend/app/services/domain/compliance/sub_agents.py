from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Set

from app.models import FileRecord

SUB_AGENT_DEFS: Dict[str, Dict[str, Any]] = {
    "meeting_plan": {
        "name": "会议计划专员",
        "station": "计划席",
        "modality": "text",
        "doc_types": {"meeting_metadata", "a1_meeting_export", "meeting_agenda"},
        "risk_categories": {"计划不一致", "未成功观察"},
        "focus_keys": {"议程", "A1", "计划", "预算", "会议编码"},
        "agent_say": "我在核对 A1 计划、议程与观察元数据是否一致。",
    },
    "attendance": {
        "name": "签到与会专员",
        "station": "签到席",
        "modality": "mixed",
        "doc_types": {"sign_in_record", "meeting_screenshot"},
        "risk_categories": {"参会人身份不符", "计划不一致"},
        "focus_keys": {"签到", "参会", "HCP", "实名"},
        "agent_say": "我在核对签到名单、线上参会与计划人数。",
    },
    "speaker": {
        "name": "讲者核验专员",
        "station": "讲者席",
        "modality": "mixed",
        "doc_types": {"speaker_profile", "presentation_material", "observation_confirmation"},
        "risk_categories": {"参会人身份不符", "违反公司制度"},
        "focus_keys": {"讲者", "演讲", "讲课", "PPT", "材料编码"},
        "agent_say": "我在核验讲者身份、服务时长与演讲材料。",
    },
    "evidence": {
        "name": "证据链专员",
        "station": "证据席",
        "modality": "mixed",
        "doc_types": {"coordination_sms", "meeting_screenshot", "observation_confirmation"},
        "risk_categories": {"未成功观察", "计划不一致"},
        "focus_keys": {"短信", "截图", "远程", "观察", "确认单"},
        "agent_say": "我在检查远程观察沟通与现场/线上证据链完整性。",
    },
    "policy": {
        "name": "合规政策专员",
        "station": "合规席",
        "modality": "mixed",
        "doc_types": {"finding_template", "observation_confirmation", "presentation_material"},
        "risk_categories": {"违反公司制度"},
        "focus_keys": {"时长", "费用", "编码", "PMA", "NP", "推广"},
        "agent_say": "我对照罗氏政策检查讲课时长、材料编码与推广性质。",
    },
}


def route_sub_agents(
    files: Iterable[FileRecord],
    plan: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    plan = plan or {}
    present = {f.document_category for f in files if f.document_category and f.document_category != "unknown"}
    focus_text = f"{_plan_items_text(plan.get('focus_areas'))} {_plan_items_text(plan.get('priority_actions'))}"

    scored: List[tuple[int, str, Dict[str, Any]]] = []
    for agent_id, cfg in SUB_AGENT_DEFS.items():
        score = 0
        if present & cfg["doc_types"]:
            score += 10 + len(present & cfg["doc_types"]) * 5
        for key in cfg["focus_keys"]:
            if key in focus_text:
                score += 8
        if score > 0:
            scored.append((score, agent_id, cfg))

    scored.sort(key=lambda x: x[0], reverse=True)
    active = scored[:4] if scored else []

    if not active and present:
        active = [(5, "meeting_plan", SUB_AGENT_DEFS["meeting_plan"])]

    return [
        {
            "id": agent_id,
            "name": cfg["name"],
            "station": cfg["station"],
            "agent_say": cfg["agent_say"],
            "score": score,
            "doc_types": sorted(cfg["doc_types"] & present) if present else sorted(cfg["doc_types"]),
        }
        for score, agent_id, cfg in active
    ]


def _plan_items_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        return " ".join(_plan_items_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_plan_items_text(item) for item in value.values())
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def pick_sub_agent_for_risk(risk: Dict[str, Any], sub_agents: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    cat = risk.get("risk_category") or ""
    for sa in sub_agents:
        cfg = SUB_AGENT_DEFS.get(sa["id"], {})
        if cat in cfg.get("risk_categories", set()):
            return sa
    return sub_agents[0] if sub_agents else None


def enrich_plan_with_sub_agents(plan: Dict[str, Any], files: Iterable[FileRecord]) -> Dict[str, Any]:
    plan = dict(plan)
    plan["sub_agents"] = route_sub_agents(files, plan)
    if plan["sub_agents"]:
        names = "、".join(sa["name"] for sa in plan["sub_agents"])
        plan.setdefault("reasoning", "")
        if names not in plan["reasoning"]:
            plan["reasoning"] = f"已调度 {names}。" + plan["reasoning"]
    return plan
