from __future__ import annotations

from typing import Any, Dict, List

from app.services.rule_engine import match_entities


def build_record_links(project_id: str, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    links: List[Dict[str, Any]] = []
    invoices = [e for e in entities if e["entity_type"] == "invoice_number"]
    amounts = [e for e in entities if e["entity_type"] == "amount"]
    suppliers = [e for e in entities if e["entity_type"] in ("supplier", "party_b", "seller_name")]

    # 发票号精确关联
    inv_groups: Dict[str, List[Dict]] = {}
    for inv in invoices:
        inv_groups.setdefault(inv["entity_value"], []).append(inv)
    for inv_no, group in inv_groups.items():
        if len(group) >= 2:
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    links.append(
                        _link(
                            project_id,
                            "invoice_number_match",
                            group[i]["file_id"],
                            group[j]["file_id"],
                            {"invoice_number": inv_no},
                            0.98,
                            "exact_invoice_no",
                        )
                    )

    # 金额 + 主体模糊关联
    for a in amounts:
        try:
            amt = float(str(a["entity_value"]).replace(",", ""))
        except ValueError:
            continue
        for b in amounts:
            if a["file_id"] == b["file_id"] and a is b:
                continue
            try:
                b_amt = float(str(b["entity_value"]).replace(",", ""))
            except ValueError:
                continue
            if abs(amt - b_amt) > 1 and abs(amt - b_amt) / max(amt, b_amt, 1) > 0.005:
                continue
            sup_a = _find_supplier(a, suppliers)
            sup_b = _find_supplier(b, suppliers)
            if sup_a and sup_b:
                m = match_entities(sup_a, sup_b)
                if m["match_result"] in ("same", "likely_same"):
                    links.append(
                        _link(
                            project_id,
                            "amount_party_match",
                            a["file_id"],
                            b["file_id"],
                            {"amount": amt, "supplier_a": sup_a, "supplier_b": sup_b},
                            m["match_score"],
                            "amount+fuzzy_supplier",
                        )
                    )
            elif abs(amt - b_amt) <= 1:
                links.append(
                    _link(
                        project_id,
                        "amount_exact_match",
                        a["file_id"],
                        b["file_id"],
                        {"amount": amt},
                        0.85,
                        "exact_amount",
                    )
                )

    return _dedupe_links(links)


def links_to_cross_risks(links: List[Dict[str, Any]], parsed_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """基于链接发现三方不匹配：有费用/合同金额但无发票链接。"""
    risks = []
    file_cats = {d["file_id"]: d["document_category"] for d in parsed_docs}
    expense_files = {fid for fid, c in file_cats.items() if c == "expense_detail"}
    invoice_files = {fid for fid, c in file_cats.items() if c in ("invoice_list", "invoice_image")}
    linked_expense = {l["source_file_id"] for l in links if l["source_file_id"] in expense_files}
    linked_expense |= {l["target_file_id"] for l in links if l.get("target_file_id") in expense_files}

    for ef in expense_files - linked_expense:
        if invoice_files:
            fname = next((d["file_name"] for d in parsed_docs if d["file_id"] == ef), ef)
            risks.append(
                {
                    "risk_id": f"LINK-{ef[:8]}",
                    "risk_category": "数据一致性风险",
                    "risk_level": "中",
                    "problem": "费用明细未能与发票清单建立关联",
                    "evidence_json": {"file_name": fname},
                    "suggestion": "请核对费用对应发票号码、销售方名称及金额是否一致。",
                    "source_file_id": ef,
                    "manual_review_required": True,
                    "rule_triggered": "LINK-001",
                }
            )
    return risks


def _find_supplier(amount_entity: Dict, suppliers: List[Dict]) -> str | None:
    loc = amount_entity.get("source_location") or {}
    row = loc.get("row")
    for s in suppliers:
        sloc = s.get("source_location") or {}
        if s["file_id"] == amount_entity["file_id"] and sloc.get("row") == row:
            return s["entity_value"]
    return None


def _link(
    project_id: str,
    link_type: str,
    source_file_id: str,
    target_file_id: str,
    keys: Dict,
    confidence: float,
    method: str,
) -> Dict:
    return {
        "project_id": project_id,
        "link_type": link_type,
        "source_file_id": source_file_id,
        "target_file_id": target_file_id,
        "link_keys": keys,
        "confidence": confidence,
        "match_method": method,
    }


def _dedupe_links(links: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for l in links:
        key = (l["link_type"], l["source_file_id"], l.get("target_file_id"), str(l["link_keys"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(l)
    return out
