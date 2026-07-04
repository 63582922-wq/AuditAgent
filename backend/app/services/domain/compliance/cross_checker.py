from __future__ import annotations

import re
from typing import Any, Dict, List

from app.models import FileRecord, ParsedDocument
from app.services.domain.compliance.template_field_engine import (
    build_template_fact_bag,
    merge_vision_consensus_fallbacks,
)


def _minutes_from_range(text: str) -> int | None:
    m = re.search(r"(\d+)\s*分钟", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{1,2}):(\d{2})\s*[-~至]\s*(\d{1,2}):(\d{2})", text)
    if m:
        h1, m1, h2, m2 = map(int, m.groups())
        return (h2 * 60 + m2) - (h1 * 60 + m1)
    return None


def _material_from_parsed_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    content = doc.get("content_json") or {}
    if not isinstance(content, dict):
        content = {}
    fields = content.get("fields") if isinstance(content.get("fields"), dict) else {}
    confidence = content.get("field_confidence") or content.get("confidence")
    if not isinstance(confidence, dict):
        confidence = {}
    fields, confidence = merge_vision_consensus_fallbacks(content, fields, confidence)
    return {
        "file_id": doc.get("file_id"),
        "file_name": doc.get("file_name") or content.get("source_file_name") or "",
        "document_category": doc.get("document_category") or content.get("document_type") or "",
        "text_content": doc.get("text_content") or content.get("text_content") or "",
        "fields": fields,
        "field_confidence": confidence,
        "sheets": content.get("sheets") or [],
        "md_results": content.get("md_results") or "",
        "vision_consensus": content.get("vision_consensus"),
    }


def _merge_template_facts(facts: Dict[str, Any], meeting_profile: Dict[str, Any], parsed_docs: List[dict]) -> None:
    materials = [_material_from_parsed_doc(doc) for doc in parsed_docs]
    fact_bag = build_template_fact_bag(meeting_profile, materials)
    evidence_overrides = {
        "actual_sign_in_count",
        "attendance_delta",
        "attendance_source",
        "watch_record_count",
        "start_attendee_count",
        "max_attendee_count",
        "end_attendee_count",
        "zoom_peak_count",
        "total_attendance_expression",
        "material_code",
        "material_code_display",
        "presentation_topic",
        "ppt_pages",
    }
    for key, value in fact_bag.values.items():
        if value in (None, "", [], {}):
            continue
        if key in evidence_overrides or facts.get(key) in (None, "", [], {}, 0):
            facts[key] = value
    if fact_bag.sources:
        facts["fact_sources"] = dict(fact_bag.sources)
    if fact_bag.confidence:
        facts["fact_confidence"] = dict(fact_bag.confidence)
    if fact_bag.evidence:
        facts["fact_evidence"] = dict(fact_bag.evidence)


def build_case_facts(
    meeting_profile: Dict[str, Any],
    files: List[FileRecord],
    parsed_docs: List[dict],
) -> Dict[str, Any]:
    categories = {f.document_category for f in files}
    facts = dict(meeting_profile)
    _merge_template_facts(facts, meeting_profile, parsed_docs)
    facts["has_a1_export"] = "a1_meeting_export" in categories
    facts["has_confirmation"] = "observation_confirmation" in categories
    facts["has_coordination_sms"] = "coordination_sms" in categories
    facts["has_sign_in"] = "sign_in_record" in categories
    facts["has_agenda"] = "meeting_agenda" in categories
    facts["has_presentation_material"] = "presentation_material" in categories

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
        sheets = doc.get("content_json", {}).get("sheets") or []

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
            for sheet in sheets:
                rows = sheet.get("rows") or []
                if not rows:
                    continue
                headers = set((rows[0].get("values") or {}).keys())
                if {"会议时间", "观众姓名", "登录时间", "登录时长"}.issubset(headers):
                    facts["attendance_source"] = "watch_record"
                    facts["watch_record_count"] = sum(1 for r in rows if (r.get("values") or {}).get("观众姓名"))

    try:
        actual = int(actual) if actual is not None else None
    except (TypeError, ValueError):
        actual = _minutes_from_range(str(actual))

    facts["actual_duration_minutes"] = actual or facts["planned_duration_minutes"]
    facts["duration_delta_minutes"] = abs(
        int(facts["actual_duration_minutes"]) - int(facts["planned_duration_minutes"])
    )
    facts["speaker_service_minutes"] = speaker_minutes or facts.get("speaker_service_minutes") or int(
        facts.get("speaker_duration") or 30
    )
    facts["material_code"] = material_code
    if facts.get("has_presentation_material") and not material_code:
        facts["material_code_pending_vision"] = True
    current_sign_in = None
    try:
        current_sign_in = int(facts.get("actual_sign_in_count")) if facts.get("actual_sign_in_count") not in (None, "") else None
    except (TypeError, ValueError):
        current_sign_in = None
    if current_sign_in is not None and current_sign_in <= 0:
        current_sign_in = None

    watch_record_only = facts.get("attendance_source") == "watch_record" and not sign_in_count and not current_sign_in
    if sign_in_count:
        actual_sign_in_count = sign_in_count
    elif current_sign_in:
        actual_sign_in_count = current_sign_in
    elif watch_record_only:
        actual_sign_in_count = None
    else:
        actual_sign_in_count = int(facts.get("planned_attendees") or 0)

    facts["actual_sign_in_count"] = actual_sign_in_count
    facts["planned_attendees"] = int(facts.get("planned_attendees") or actual_sign_in_count or 7)
    facts["attendance_delta"] = (
        None if actual_sign_in_count is None else abs(actual_sign_in_count - facts["planned_attendees"])
    )
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
        rule_id = str(rule.get("rule_id") or "")
        meeting_code = str(facts.get("meeting_code") or "")
        if rule_id == "CMP-004" and meeting_code.startswith("SMS"):
            continue
        if rule_id == "CMP-005" and facts.get("material_code_pending_vision"):
            continue
        if rule_id == "CMP-006" and facts.get("attendance_source") == "watch_record":
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
