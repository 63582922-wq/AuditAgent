from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set

from app.models import FileRecord

SUB_AGENT_DEFS: Dict[str, Dict[str, Any]] = {
    "tax": {
        "name": "税务专员",
        "station": "税务席",
        "doc_types": {"tax_return", "invoice_list", "expense_detail"},
        "risk_categories": {"税务风险"},
        "focus_keys": {"税务", "增值税", "税负", "进项", "销项"},
        "agent_say": "我在核对税务申报与发票、费用之间的勾稽。",
    },
    "invoice": {
        "name": "票据专员",
        "station": "票据席",
        "doc_types": {"invoice_list", "invoice_image", "expense_detail"},
        "risk_categories": {"税务风险", "票据风险"},
        "focus_keys": {"发票", "票据", "重复", "连号"},
        "agent_say": "我在检查发票完整性、重复性与合规性。",
    },
    "contract": {
        "name": "合同专员",
        "station": "合同席",
        "doc_types": {"contract"},
        "risk_categories": {"合同风险"},
        "focus_keys": {"合同", "协议", "条款"},
        "agent_say": "我在审阅合同条款与后续票据、流水是否匹配。",
    },
    "treasury": {
        "name": "资金专员",
        "station": "资金席",
        "doc_types": {"bank_statement", "expense_detail"},
        "risk_categories": {"异常交易风险", "会计核算风险"},
        "focus_keys": {"银行", "流水", "资金", "收付"},
        "agent_say": "我在核对账面记录与银行流水的一致性。",
    },
    "ledger": {
        "name": "账务专员",
        "station": "账务席",
        "doc_types": {"trial_balance", "accounts_payable", "accounts_receivable"},
        "risk_categories": {"会计核算风险"},
        "focus_keys": {"科目", "余额", "账务", "借贷"},
        "agent_say": "我在检查科目余额与明细账的合理性。",
    },
}


def route_sub_agents(
    files: Iterable[FileRecord],
    plan: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    plan = plan or {}
    present = {f.document_category for f in files if f.document_category and f.document_category != "unknown"}
    focus_text = " ".join(plan.get("focus_areas") or []) + " ".join(plan.get("priority_actions") or [])

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
        active = [(5, "tax", SUB_AGENT_DEFS["tax"])]

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
