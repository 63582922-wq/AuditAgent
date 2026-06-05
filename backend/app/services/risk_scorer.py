from __future__ import annotations

from typing import Any


def score_amount(amount: Any) -> int:
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        return 1
    if amt < 1000:
        return 1
    if amt < 10000:
        return 2
    if amt < 50000:
        return 3
    if amt < 100000:
        return 4
    return 5


def level_from_score(total: int) -> str:
    if total <= 7:
        return "低"
    if total <= 15:
        return "中"
    return "高"


SEVERITY_MAP = {"低": 2, "中": 3, "高": 5}


def calculate_risk_score(rule_level: str, evidence: dict[str, Any], confidence: float) -> dict:
    severity = SEVERITY_MAP.get(rule_level, 3)
    amount = evidence.get("amount") or evidence.get("total_amount") or evidence.get("contract_amount") or 0
    amount_score = score_amount(amount)
    evidence_score = 4 if evidence else 2
    probability_score = 4
    compliance_score = severity
    confidence_penalty = 0 if confidence >= 0.85 else 1

    total = severity + amount_score + evidence_score + probability_score + compliance_score - confidence_penalty
    total = max(0, min(total, 25))
    return {
        "severity_score": severity,
        "amount_score": amount_score,
        "evidence_score": evidence_score,
        "probability_score": probability_score,
        "compliance_score": compliance_score,
        "total_score": total,
        "risk_level": level_from_score(total),
    }
