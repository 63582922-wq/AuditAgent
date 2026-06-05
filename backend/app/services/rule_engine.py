from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from app.services.classifier import clean_entity_name


def evaluate_condition(row: dict[str, Any], condition: dict) -> bool:
    if "all" in condition:
        return all(_eval_single(row, c) for c in condition["all"])
    if "any" in condition:
        return any(_eval_single(row, c) for c in condition["any"])
    return _eval_single(row, condition)


def _eval_single(row: dict[str, Any], cond: dict) -> bool:
    field = cond.get("field")
    op = cond.get("operator")
    value = cond.get("value")
    actual = _get_field_value(row, field)

    if op == "is_empty":
        return actual in (None, "", 0, "0")
    if op == "is_not_empty":
        return actual not in (None, "", 0, "0")
    if op == ">=":
        try:
            return float(actual) >= float(value)
        except (TypeError, ValueError):
            return False
    if op == ">":
        try:
            return float(actual) > float(value)
        except (TypeError, ValueError):
            return False
    if op == "<=":
        try:
            return float(actual) <= float(value)
        except (TypeError, ValueError):
            return False
    if op == "<":
        try:
            return float(actual) < float(value)
        except (TypeError, ValueError):
            return False
    if op == "==":
        return str(actual) == str(value)
    if op == "contains":
        return str(value) in str(actual)
    return False


def _get_field_value(row: dict[str, Any], field: str) -> Any:
    if field in row:
        return row[field]
    for k, v in row.items():
        if field in str(k):
            return v
    return ""


def run_rules_on_rows(
    rows: list[dict],
    rules: list[dict],
    file_meta: dict,
) -> list[dict]:
    hits: list[dict] = []
    seen: set[str] = set()

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        if rule.get("applicable_document_type") not in (
            file_meta.get("document_category"),
            "*",
        ):
            continue

        for row_ctx in rows:
            values = row_ctx.get("values", row_ctx)
            std_row = _standardize_row(values, row_ctx.get("columns_map", {}))
            if not evaluate_condition(std_row, rule["condition_json"]):
                continue

            dedupe = f"{rule['rule_id']}:{row_ctx.get('row_number')}:{file_meta.get('file_id')}"
            if dedupe in seen:
                continue
            seen.add(dedupe)

            evidence = {f: std_row.get(f, values.get(f, "")) for f in rule.get("evidence_fields", [])}
            hits.append(
                {
                    "rule": rule,
                    "row_ctx": row_ctx,
                    "std_row": std_row,
                    "evidence": evidence,
                }
            )
    return hits


def _standardize_row(values: dict, columns_map: dict) -> dict:
    out = dict(values)
    for col_name, std in columns_map.items():
        if std and col_name in values:
            out[std] = values[col_name]
    alias_map = {
        "amount": ["金额", "价税合计", "报销金额", "发生额"],
        "invoice_number": ["发票号", "发票号码", "票号"],
        "summary": ["摘要", "用途", "备注", "科目名称"],
        "date": ["日期", "发生日期", "开票日期"],
        "debit": ["借方", "借方金额", "借方发生"],
        "credit": ["贷方", "贷方金额", "贷方发生"],
        "tax_amount": ["税额", "税金"],
        "tax_rate": ["税率"],
    }
    for std, keys in alias_map.items():
        if std in out and out[std] not in ("", None):
            continue
        for k, v in values.items():
            if any(alias in k for alias in keys) and v not in ("", None):
                out[std] = v
                break
    if not out.get("amount") or out.get("amount") in ("", None):
        for k in ("debit", "credit", "借方发生", "贷方发生"):
            v = out.get(k) or values.get(k)
            if v not in (None, "", 0):
                try:
                    if float(str(v).replace(",", "")) != 0:
                        out["amount"] = v
                        break
                except ValueError:
                    pass
    return out


def run_rules_on_fields(
    fields: dict[str, Any],
    rules: list[dict],
    file_meta: dict,
) -> list[dict]:
    hits: list[dict] = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        if rule.get("applicable_document_type") not in (
            file_meta.get("document_category"),
            "*",
        ):
            continue
        if not evaluate_condition(fields, rule["condition_json"]):
            continue
        evidence = {f: fields.get(f, "") for f in rule.get("evidence_fields", [])}
        hits.append(
            {
                "rule": rule,
                "row_ctx": {"row_number": 1, "sheet_name": "fields", "values": fields},
                "std_row": fields,
                "evidence": evidence,
            }
        )
    return hits


def match_entities(name_a: str, name_b: str) -> dict:
    a = clean_entity_name(name_a)
    b = clean_entity_name(name_b)
    score = fuzz.token_sort_ratio(a, b) / 100
    result = "same" if score >= 0.92 else "likely_same" if score >= 0.75 else "different"
    return {
        "entity_a": name_a,
        "entity_b": name_b,
        "match_score": round(score, 2),
        "match_result": result,
        "needs_manual_review": 0.75 <= score < 0.92,
    }
