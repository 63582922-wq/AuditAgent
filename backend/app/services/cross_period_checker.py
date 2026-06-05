from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


def _parse_date(val: Any) -> Optional[datetime]:
    if val is None or val == "":
        return None
    s = str(val).replace("年", "-").replace("月", "-").replace("日", "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


def detect_cross_period_risks(rows: List[Dict[str, Any]], file_id: str, file_name: str) -> List[Dict]:
    """检测业务日期与入账日期跨年度等跨期风险。"""
    risks = []
    for row in rows:
        vals = row.get("values", row)
        business = _parse_date(vals.get("date") or vals.get("business_date"))
        booking = _parse_date(vals.get("booking_date") or vals.get("入账日期"))
        if not business or not booking:
            continue
        if business.year != booking.year and abs((booking - business).days) > 30:
            risks.append(
                {
                    "risk_id": f"CROSS-{row.get('row_number', 0)}",
                    "risk_category": "会计核算风险",
                    "risk_level": "中",
                    "problem": "费用可能存在跨期入账",
                    "evidence_json": {
                        "business_date": business.strftime("%Y-%m-%d"),
                        "booking_date": booking.strftime("%Y-%m-%d"),
                        "amount": vals.get("amount") or vals.get("金额"),
                    },
                    "suggestion": "请核实该费用归属期间，必要时调整至正确会计期间。",
                    "source_file_id": file_id,
                    "source_location_json": {"sheet": row.get("sheet_name"), "row": row.get("row_number")},
                    "manual_review_required": True,
                    "rule_triggered": "CROSS-001",
                    "related_files": [file_name],
                }
            )
        if (booking - business).days > 90:
            risks.append(
                {
                    "risk_id": f"CROSS-LATE-{row.get('row_number', 0)}",
                    "risk_category": "税务风险",
                    "risk_level": "中",
                    "problem": "发票/业务日期远早于入账日期",
                    "evidence_json": {
                        "business_date": business.strftime("%Y-%m-%d"),
                        "booking_date": booking.strftime("%Y-%m-%d"),
                        "days_gap": (booking - business).days,
                    },
                    "suggestion": "请核实是否存在滞后入账或补票情况。",
                    "source_file_id": file_id,
                    "source_location_json": {"sheet": row.get("sheet_name"), "row": row.get("row_number")},
                    "manual_review_required": True,
                    "rule_triggered": "CROSS-002",
                    "related_files": [file_name],
                }
            )
    return risks


def detect_three_way_gaps(
    parsed_docs: List[Dict[str, Any]],
    links: List[Dict[str, Any]],
) -> List[Dict]:
    """合同-发票-付款三方匹配缺口检测。"""
    risks = []
    cats = {d["file_id"]: d["document_category"] for d in parsed_docs}
    has_contract = any(c == "contract" for c in cats.values())
    has_invoice = any(c in ("invoice_list", "invoice_image") for c in cats.values())
    has_bank = any(c == "bank_statement" for c in cats.values())

    if has_contract and has_invoice and not links:
        risks.append(
            {
                "risk_id": "3WAY-001",
                "risk_category": "数据一致性风险",
                "risk_level": "高",
                "problem": "存在合同与发票资料但未能建立记录关联",
                "evidence_json": {"has_contract": True, "has_invoice": True, "link_count": 0},
                "suggestion": "请核对合同号、发票号码、销售方名称及金额是否一致。",
                "manual_review_required": True,
                "rule_triggered": "3WAY-001",
            }
        )

    if has_invoice and has_bank:
        bank_linked = any(
            l["link_type"] in ("amount_exact_match", "amount_party_match")
            and (
                cats.get(l["source_file_id"]) == "bank_statement"
                or cats.get(l.get("target_file_id", "")) == "bank_statement"
            )
            for l in links
        )
        if not bank_linked:
            risks.append(
                {
                    "risk_id": "3WAY-002",
                    "risk_category": "银行流水风险",
                    "risk_level": "中",
                    "problem": "发票与银行流水未能建立付款关联",
                    "evidence_json": {"has_invoice": True, "has_bank": True},
                    "suggestion": "请核对发票对应付款是否已在银行流水中体现。",
                    "manual_review_required": True,
                    "rule_triggered": "3WAY-002",
                }
            )
    return risks
