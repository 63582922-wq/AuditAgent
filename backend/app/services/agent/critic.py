from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set


@dataclass
class CriticResult:
    risk_id: str
    valid: bool
    flags: List[str] = field(default_factory=list)
    score: float = 1.0
    message: str = ""


def _extract_numbers(obj: Any) -> Set[str]:
    nums: Set[str] = set()
    if obj is None:
        return nums
    if isinstance(obj, (int, float)):
        nums.add(str(int(obj) if float(obj).is_integer() else round(float(obj), 2)))
        return nums
    if isinstance(obj, str):
        for m in re.finditer(r"\d[\d,]*\.?\d*", obj.replace(",", "")):
            raw = m.group().replace(",", "")
            try:
                val = float(raw)
                nums.add(str(int(val) if val.is_integer() else round(val, 2)))
            except ValueError:
                nums.add(raw)
        return nums
    if isinstance(obj, dict):
        for v in obj.values():
            nums.update(_extract_numbers(v))
    elif isinstance(obj, list):
        for v in obj:
            nums.update(_extract_numbers(v))
    return nums


def _numbers_in_text(text: str) -> Set[str]:
    return _extract_numbers(text)


def validate_risk_evidence(risk: Dict[str, Any]) -> CriticResult:
    """规则层证据链校验：analysis 中的数字应能在 evidence 中找到。"""
    rid = str(risk.get("risk_id") or "")
    analysis = str(risk.get("analysis") or "")
    evidence = risk.get("evidence_json") or {}

    if not analysis:
        return CriticResult(risk_id=rid, valid=True, score=1.0, message="无 analysis，跳过")

    evidence_nums = _extract_numbers(evidence)
    analysis_nums = _numbers_in_text(analysis)

    # 忽略常见小数字（行号、百分比片段）
    significant = {n for n in analysis_nums if len(n.replace(".", "")) >= 3 or float(n) >= 100}

    if not significant:
        return CriticResult(risk_id=rid, valid=True, score=1.0, message="无显著数值引用")

    unmatched = []
    for num in significant:
        if num in evidence_nums:
            continue
        # 允许整数/小数等价
        try:
            f = float(num)
            if any(abs(f - float(e)) < 0.01 for e in evidence_nums if e.replace(".", "").isdigit()):
                continue
        except ValueError:
            pass
        unmatched.append(num)

    if unmatched:
        return CriticResult(
            risk_id=rid,
            valid=False,
            flags=[f"unverified_number:{n}" for n in unmatched],
            score=max(0.2, 1.0 - 0.2 * len(unmatched)),
            message=f"analysis 引用了 evidence 中未出现的数值: {', '.join(unmatched)}",
        )

    return CriticResult(risk_id=rid, valid=True, score=1.0, message="证据链一致")


def validate_risks(risks: List[Dict[str, Any]]) -> List[CriticResult]:
    return [validate_risk_evidence(r) for r in risks if r.get("analysis")]


def apply_critic_to_risks(
    risks: List[Dict[str, Any]], results: List[CriticResult]
) -> List[Dict[str, Any]]:
    by_id = {r.risk_id: r for r in results}
    out: List[Dict[str, Any]] = []
    for risk in risks:
        merged = dict(risk)
        cr = by_id.get(str(risk.get("risk_id") or ""))
        if cr and not cr.valid:
            merged["manual_review_required"] = True
            merged["critic_flags"] = cr.flags
            merged["critic_message"] = cr.message
            conf = float(merged.get("confidence") or 0.9)
            merged["confidence"] = min(conf, cr.score)
        out.append(merged)
    return out
