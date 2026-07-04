from __future__ import annotations

import uuid
from typing import Any


def amount_within_tolerance(a: float, b: float, base: float | None = None) -> str:
    diff = abs(a - b)
    if diff == 0:
        return "exact"
    if diff <= 1:
        return "small_tail"
    base_amt = base or max(abs(a), abs(b), 1)
    if diff / base_amt <= 0.005:
        return "reasonable"
    return "abnormal"


def cross_check_amounts(documents: list[dict[str, Any]]) -> list[dict]:
    risks: list[dict] = []
    contracts: list[dict] = []
    invoices: list[dict] = []
    expenses: list[dict] = []

    for doc in documents:
        cat = doc.get("document_category")
        content = doc.get("content_json", {})
        if cat == "contract":
            fields = content.get("fields") or {}
            amt = fields.get("contract_amount")
            if amt:
                contracts.append({"file_id": doc["file_id"], "file_name": doc["file_name"], "amount": float(amt)})
        elif cat == "invoice_list":
            for sheet in content.get("sheets", []):
                for row in sheet.get("rows", []):
                    vals = row.get("values", {})
                    amt = _pick_amount(vals)
                    if amt:
                        invoices.append(
                            {
                                "file_id": doc["file_id"],
                                "file_name": doc["file_name"],
                                "amount": amt,
                                "row": row.get("row_number"),
                                "invoice_number": _pick(vals, ["invoice_number", "发票号", "发票号码"]),
                            }
                        )
        elif cat == "expense_detail":
            for sheet in content.get("sheets", []):
                for row in sheet.get("rows", []):
                    vals = row.get("values", {})
                    amt = _pick_amount(vals)
                    if amt:
                        expenses.append(
                            {
                                "file_id": doc["file_id"],
                                "file_name": doc["file_name"],
                                "amount": amt,
                                "row": row.get("row_number"),
                                "sheet": sheet.get("sheet_name"),
                                "summary": _pick(vals, ["summary", "摘要", "用途"]),
                                "invoice_number": _pick(vals, ["invoice_number", "发票号", "发票号码"]),
                            }
                        )

    for contract in contracts:
        inv_total = sum(i["amount"] for i in invoices)
        if inv_total and contract["amount"]:
            status = amount_within_tolerance(contract["amount"], inv_total, contract["amount"])
            if status == "abnormal":
                risks.append(
                    _make_cross_risk(
                        "AMT-001",
                        "数据一致性风险",
                        "中",
                        "合同金额与发票累计金额不一致",
                        {
                            "contract_amount": contract["amount"],
                            "invoice_total": inv_total,
                            "difference": contract["amount"] - inv_total,
                        },
                        "请核实是否存在未开票金额、合同变更或发票缺失。",
                        related=[contract["file_name"]] + list({i["file_name"] for i in invoices}),
                    )
                )

    for exp in expenses:
        for inv in invoices:
            if not _same_invoice_pair(exp, inv):
                continue
            if abs(exp["amount"] - inv["amount"]) <= 1:
                continue
            if abs(exp["amount"] - inv["amount"]) / max(exp["amount"], inv["amount"], 1) <= 0.005:
                continue
            risks.append(
                _make_cross_risk(
                    "AMT-002",
                    "数据一致性风险",
                    "中",
                    "费用明细金额与发票金额不一致",
                    {
                        "expense_amount": exp["amount"],
                        "invoice_amount": inv["amount"],
                        "invoice_number": inv.get("invoice_number"),
                        "difference": exp["amount"] - inv["amount"],
                    },
                    "请核对费用明细与发票是否为同一笔业务。",
                    related=[exp["file_name"], inv["file_name"]],
                    source_file_id=exp["file_id"],
                    source_location={"sheet": exp.get("sheet"), "row": exp.get("row")},
                )
            )
    return risks


def detect_duplicate_invoices(rows: list[dict]) -> list[dict]:
    seen: dict[str, list] = {}
    risks = []
    for row in rows:
        inv_no = row.get("invoice_number")
        if not inv_no:
            continue
        seen.setdefault(inv_no, []).append(row)
    for inv_no, group in seen.items():
        if len(group) > 1:
            risks.append(
                _make_cross_risk(
                    "INV-001",
                    "票据风险",
                    "高",
                    "发现重复发票号码",
                    {
                        "invoice_number": inv_no,
                        "rows": [g.get("row") for g in group],
                        "files": list({g.get("file_name") for g in group if g.get("file_name")}),
                    },
                    "请核实是否重复报销或重复入账。",
                    related=list({g.get("file_name") for g in group if g.get("file_name")}),
                )
            )
    return risks


def check_missing_documents(
    present_categories: set[str],
    *,
    domain: str | None = None,
    meeting_case: dict[str, Any] | None = None,
) -> list[dict]:
    from app.services.domain.registry import get_domain_pack

    pack = get_domain_pack(domain=domain) if domain else get_domain_pack()
    meeting_case = meeting_case or {}
    meeting_code = str(meeting_case.get("meeting_code") or "")
    reality_evidence = {
        "meeting_screenshot",
        "coordination_sms",
        "observation_confirmation",
        "sign_in_record",
        "other_supporting_evidence",
    }
    has_alternative_reality_evidence = len(present_categories & reality_evidence) >= 2
    missing = []
    for doc_type, importance, reason in pack.required_docs:
        if domain == "compliance":
            if doc_type == "meeting_metadata" and meeting_case.get("meeting_code") and meeting_case.get("observation_type"):
                continue
            if doc_type == "a1_meeting_export" and meeting_code.startswith("SMS"):
                continue
            if doc_type == "meeting_screenshot" and has_alternative_reality_evidence:
                continue
        if doc_type not in present_categories:
            missing.append({"document_type": doc_type, "importance": importance, "reason": reason})
    return missing


def _pick_amount(vals: dict) -> float | None:
    for key in ["amount", "价税合计", "金额", "报销金额", "合计", "借方发生", "贷方发生"]:
        if key in vals and vals[key] not in ("", None):
            try:
                return float(str(vals[key]).replace(",", ""))
            except (TypeError, ValueError):
                pass
    for k, v in vals.items():
        if "金额" in k or "合计" in k:
            try:
                return float(str(v).replace(",", ""))
            except (TypeError, ValueError):
                pass
    return None


def _pick(vals: dict, keys: list[str]) -> str:
    for k in keys:
        if k in vals and vals[k]:
            return str(vals[k])
    return ""


def _same_invoice_pair(exp: dict, inv: dict) -> bool:
    exp_inv = (exp.get("invoice_number") or "").strip()
    inv_inv = (inv.get("invoice_number") or "").strip()
    if exp_inv and inv_inv:
        return exp_inv == inv_inv
    return False


def _make_cross_risk(
    risk_code: str,
    category: str,
    level: str,
    problem: str,
    evidence: dict,
    suggestion: str,
    related: list | None = None,
    source_file_id: str | None = None,
    source_location: dict | None = None,
) -> dict:
    return {
        "risk_id": f"{risk_code}-{uuid.uuid4().hex[:8]}",
        "risk_category": category,
        "risk_level": level,
        "problem": problem,
        "evidence_json": evidence,
        "suggestion": suggestion,
        "related_files": related or [],
        "source_file_id": source_file_id,
        "source_location_json": source_location,
        "manual_review_required": True,
        "rule_triggered": risk_code,
    }
