from __future__ import annotations

import re
from typing import Any, Dict, List

from app.models import FileRecord, ParsedDocument


def _minutes_from_range(text: str) -> int | None:
    m = re.search(r"(\d+)\s*分钟", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{1,2}):(\d{2})\s*[-~至]\s*(\d{1,2}):(\d{2})", text)
    if m:
        h1, m1, h2, m2 = map(int, m.groups())
        return (h2 * 60 + m2) - (h1 * 60 + m1)
    return None


def build_case_facts(
    meeting_profile: Dict[str, Any],
    files: List[FileRecord],
    parsed_docs: List[dict],
) -> Dict[str, Any]:
    categories = {f.document_category for f in files}
    facts = dict(meeting_profile)
    facts["has_a1_export"] = "a1_meeting_export" in categories
    facts["has_confirmation"] = "observation_confirmation" in categories
    facts["has_coordination_sms"] = "coordination_sms" in categories
    facts["has_sign_in"] = "sign_in_record" in categories
    facts["has_agenda"] = "meeting_agenda" in categories

    planned = facts.get("planned_duration_minutes")
    if planned is None:
        for doc in parsed_docs:
            if doc.get("document_category") == "meeting_agenda":
                text = doc.get("text_content") or ""
                fields = doc.get("content_json", {}).get("fields") or {}
                planned = fields.get("planned_duration_minutes") or _minutes_from_range(text)
                if planned:
                    break
    facts["planned_duration_minutes"] = planned or 30

    actual = facts.get("actual_duration_minutes") or facts.get("speaker_duration")
    sign_in_count = 0
    material_code = facts.get("material_code") or ""
    speaker_minutes = None

    for doc in parsed_docs:
        cat = doc.get("document_category")
        text = doc.get("text_content") or ""
        fields = doc.get("content_json", {}).get("fields") or {}

        if cat == "observation_confirmation":
            if not actual:
                actual = _minutes_from_range(text) or fields.get("actual_duration_minutes")
            speaker_minutes = fields.get("speaker_service_minutes")
            if not speaker_minutes:
                sm = re.search(r"共计\s*(\d+)\s*分钟", text)
                if sm:
                    speaker_minutes = int(sm.group(1))
            if not material_code:
                mc = re.search(r"(M-CN-\d+|Promotional[^\s]+)", text)
                if mc:
                    material_code = mc.group(1)
            if fields.get("speaker_name") and not facts.get("speaker_name"):
                facts["speaker_name"] = fields["speaker_name"]
            if fields.get("material_code"):
                material_code = fields["material_code"]

        if cat == "sign_in_record":
            if fields.get("actual_sign_in_count"):
                sign_in_count += int(fields["actual_sign_in_count"])
            else:
                sign_in_count += len(re.findall(r"已签到", text))

    try:
        actual = int(actual) if actual is not None else None
    except (TypeError, ValueError):
        actual = _minutes_from_range(str(actual))

    facts["actual_duration_minutes"] = actual or facts["planned_duration_minutes"]
    facts["duration_delta_minutes"] = abs(
        int(facts["actual_duration_minutes"]) - int(facts["planned_duration_minutes"])
    )
    facts["speaker_service_minutes"] = speaker_minutes or int(facts.get("speaker_duration") or 30)
    facts["material_code"] = material_code
    facts["actual_sign_in_count"] = sign_in_count or int(facts.get("planned_attendees") or 0)
    facts["planned_attendees"] = int(facts.get("planned_attendees") or facts["actual_sign_in_count"] or 7)
    facts["attendance_delta"] = abs(facts["actual_sign_in_count"] - facts["planned_attendees"])
    return facts


def run_compliance_checks(facts: Dict[str, Any], rules: List[dict]) -> List[dict]:
    from app.services.rule_engine import evaluate_condition

    row = {**facts}
    for k, v in list(row.items()):
        if isinstance(v, bool):
            row[k] = "true" if v else "false"

    hits: List[dict] = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        cond = rule.get("condition_json") or rule.get("condition")
        if not cond:
            continue
        if evaluate_condition(row, cond):
            hits.append(
                {
                    "risk_id": rule["rule_id"],
                    "risk_category": rule["risk_category"],
                    "risk_level": rule["risk_level"],
                    "problem": rule["rule_name"],
                    "suggestion": rule["suggestion_template"],
                    "rule_triggered": rule["rule_id"],
                    "evidence_json": {f: facts.get(f) for f in rule.get("evidence_fields", []) if facts.get(f) is not None},
                    "manual_review_required": rule.get("manual_review_required", False),
                    "confidence": 0.92,
                }
            )
    return hits
