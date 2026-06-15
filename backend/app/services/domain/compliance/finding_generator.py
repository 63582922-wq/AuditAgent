from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.agent.llm_client import chat_json, llm_available


def load_finding_templates() -> List[Dict[str, Any]]:
    path = Path(__file__).resolve().parents[4] / "rules" / "compliance_finding_templates.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def generate_finding_narratives(
    hits: List[dict],
    meeting_profile: Dict[str, Any],
    observation_type: str = "Remote",
) -> List[dict]:
    """为规则命中项生成 Remote Finding 描述。"""
    if not hits:
        return hits

    templates = {t["check_point"]: t for t in load_finding_templates()}
    if not llm_available():
        return [{**h, "analysis": h.get("suggestion") or h.get("problem", "")} for h in hits]

    items = []
    for h in hits:
        tpl = templates.get(h["problem"], {})
        items.append(
            {
                "risk_id": h["risk_id"],
                "problem": h["problem"],
                "category": h["risk_category"],
                "template_hint": tpl.get("remote_template", "")[:500],
                "evidence": h.get("evidence_json", {}),
            }
        )

    prompt = (
        f"你是罗氏会议合规观察 Agent。观察类型：{observation_type}。\n"
        f"会议案件：{json.dumps(meeting_profile, ensure_ascii=False)[:2000]}\n"
        f"命中检查点：{json.dumps(items, ensure_ascii=False)}\n"
        "为每项输出 Remote Finding 描述（中文，80-200字，引用证据中的事实）。"
        "输出 JSON：{\"findings\":[{\"risk_id\":\"\",\"analysis\":\"\",\"risk_level\":\"高/中/低\"}]}"
    )
    try:
        result = chat_json(
            [{"role": "user", "content": prompt}],
            schema_hint='{"findings":[{"risk_id":"","analysis":"","risk_level":""}]}',
        )
        by_id = {f["risk_id"]: f for f in result.get("findings") or []}
        out = []
        for h in hits:
            merged = dict(h)
            patch = by_id.get(h["risk_id"])
            if patch:
                merged["analysis"] = patch.get("analysis") or h["suggestion"]
                if patch.get("risk_level") in ("高", "中", "低"):
                    merged["risk_level"] = patch["risk_level"]
            else:
                merged["analysis"] = h["suggestion"]
            out.append(merged)
        return out
    except Exception:
        return [{**h, "analysis": h["suggestion"]} for h in hits]
