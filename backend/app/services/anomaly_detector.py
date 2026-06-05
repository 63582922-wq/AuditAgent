from __future__ import annotations

from statistics import median
from typing import Any, Dict, List


def detect_amount_anomalies(rows: List[Dict[str, Any]], group_key: str = "summary") -> List[Dict]:
    """IQR 异常金额检测（按摘要/科目分组）。"""
    groups: Dict[str, List[float]] = {}
    row_map: Dict[str, List[Dict]] = {}

    for row in rows:
        vals = row.get("values", row)
        amt = _to_float(vals.get("amount") or vals.get("金额"))
        if amt is None:
            continue
        g = str(vals.get(group_key) or vals.get("摘要") or "default")
        groups.setdefault(g, []).append(amt)
        row_map.setdefault(g, []).append(row)

    risks = []
    for g, amounts in groups.items():
        if len(amounts) < 4:
            continue
        sorted_amt = sorted(amounts)
        q1 = sorted_amt[len(sorted_amt) // 4]
        q3 = sorted_amt[(3 * len(sorted_amt)) // 4]
        iqr = q3 - q1
        upper = q3 + 1.5 * iqr
        med = median(amounts)
        for row in row_map[g]:
            vals = row.get("values", row)
            amt = _to_float(vals.get("amount") or vals.get("金额"))
            if amt is None or amt <= upper:
                continue
            risks.append(
                {
                    "risk_id": f"ANOM-{row.get('row_number', 0)}",
                    "risk_category": "异常交易风险",
                    "risk_level": "中",
                    "problem": f"该笔费用金额 {amt:,.0f} 元显著高于同类「{g}」水平（中位数 {med:,.0f}）",
                    "evidence_json": {"amount": amt, "group": g, "median": med, "upper_bound": upper},
                    "suggestion": "建议核查合同、发票、付款记录及业务真实性。",
                    "manual_review_required": True,
                    "rule_triggered": "ANOM-IQR",
                    "source_location_json": {
                        "sheet": row.get("sheet_name"),
                        "row": row.get("row_number"),
                    },
                }
            )
    return risks


def _to_float(val: Any) -> float | None:
    try:
        return float(str(val).replace(",", ""))
    except (TypeError, ValueError):
        return None
