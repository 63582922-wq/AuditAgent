from __future__ import annotations

"""Evidence-first facts for compliance cases.

The existing parsers remain responsible for extraction.  This module records
what they observed, arbitrates by field-specific source priority, and exposes a
small, auditable fact ledger to the rules, deliverables, and Main Agent.
"""

import json
from collections import defaultdict
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models import EvidenceClaim, FactDecision, FileRecord, ParsedDocument


FACT_FIELDS = {
    "meeting_code",
    "actual_date",
    "actual_start_time",
    "actual_end_time",
    "actual_platform",
    "start_attendee_count",
    "max_attendee_count",
    "end_attendee_count",
    "actual_sign_in_count",
    "planned_attendees",
    "speaker_name",
    "speaker_service_minutes",
    "actual_duration_minutes",
    "observation_success",
    "presentation_topic",
    "material_code",
    "ppt_pages",
    "planned_date",
    "planned_start_time",
    "planned_end_time",
    "planned_duration_minutes",
    "total_budget",
    "meeting_type",
    "planned_organizer_name",
    "actual_organizer_name",
    "applicant",
    "bu",
    "product_name",
}

ACTUAL_FACTS = {
    "actual_date",
    "actual_start_time",
    "actual_end_time",
    "actual_platform",
    "start_attendee_count",
    "max_attendee_count",
    "end_attendee_count",
    "actual_sign_in_count",
    "speaker_name",
    "speaker_service_minutes",
    "actual_duration_minutes",
    "observation_success",
}
PRESENTATION_FACTS = {"presentation_topic", "material_code", "ppt_pages"}
PLAN_FACTS = {
    "planned_date",
    "planned_start_time",
    "planned_end_time",
    "planned_duration_minutes",
    "planned_attendees",
    "total_budget",
    "meeting_type",
    "planned_organizer_name",
    "applicant",
    "bu",
    "product_name",
}


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and value.strip() not in {"N/A", "待补充/需核实", "无法判断"}
    if isinstance(value, (int, float)):
        return value > 0
    return bool(value)


def _normal(value: Any) -> str:
    if isinstance(value, str):
        return "".join(value.lower().split()).replace("＋", "+")
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _priority(field: str, category: str) -> int:
    if field in ACTUAL_FACTS:
        return {
            "observation_confirmation": 100,
            "meeting_screenshot": 90,
            "sign_in_record": 88 if field == "actual_sign_in_count" else 65,
            "coordination_sms": 55,
            "a1_meeting_export": 25,
            "meeting_agenda": 15,
        }.get(category, 30)
    if field in PRESENTATION_FACTS:
        return {
            "presentation_material": 100,
            "observation_confirmation": 86,
            "meeting_agenda": 55,
            "meeting_screenshot": 45,
        }.get(category, 25)
    if field in PLAN_FACTS:
        return {
            "a1_meeting_export": 100,
            "meeting_agenda": 90,
            "meeting_metadata": 88,
            "observation_confirmation": 35,
        }.get(category, 30)
    return 30


def _field_confidence(fields: dict[str, Any], field: str, fallback: float) -> float:
    values = fields.get("field_confidence")
    if isinstance(values, dict):
        try:
            return max(0.0, min(float(values.get(field, fallback)), 1.0))
        except (TypeError, ValueError):
            pass
    try:
        return max(0.0, min(float(fields.get("vision_confidence") or fields.get("confidence") or fallback), 1.0))
    except (TypeError, ValueError):
        return fallback


def _iter_field_sets(content: dict[str, Any]) -> Iterable[tuple[dict[str, Any], int | None, str | None, str]]:
    fields = content.get("fields")
    if isinstance(fields, dict):
        yield fields, None, None, "primary"
    for item in content.get("vision_slices") or []:
        if not isinstance(item, dict):
            continue
        nested = item.get("content_json")
        if not isinstance(nested, dict) or not isinstance(nested.get("fields"), dict):
            continue
        yield (
            nested["fields"],
            item.get("page_number") or nested.get("page_number"),
            item.get("slice_id") or nested.get("slice_id"),
            "pdf_vision_slice",
        )


def _claim_from_fields(
    *,
    run_id: str,
    project_id: str,
    meeting_id: str,
    file_record: FileRecord,
    category: str,
    fields: dict[str, Any],
    page_number: int | None,
    region_id: str | None,
    extraction_pass: str,
    evidence_text: str,
) -> list[EvidenceClaim]:
    claims: list[EvidenceClaim] = []
    for key in FACT_FIELDS:
        value = fields.get(key)
        if not _is_present(value):
            continue
        confidence = _field_confidence(fields, key, float(file_record.confidence or 0.55))
        claims.append(
            EvidenceClaim(
                run_id=run_id,
                project_id=project_id,
                meeting_id=meeting_id,
                file_id=file_record.id,
                claim_key=key,
                value_json=value,
                source_kind="parsed_document",
                source_priority=_priority(key, category),
                extraction_pass=extraction_pass,
                page_number=page_number,
                region_json={"slice_id": region_id} if region_id else None,
                evidence_text=evidence_text[:1200] if evidence_text else None,
                confidence=confidence,
                status="needs_review" if confidence < 0.55 else "accepted",
            )
        )
    return claims


def _facts_to_claims(
    *,
    run_id: str,
    project_id: str,
    meeting_id: str,
    facts: dict[str, Any],
) -> list[EvidenceClaim]:
    claims: list[EvidenceClaim] = []
    for key in FACT_FIELDS:
        value = facts.get(key)
        if not _is_present(value):
            continue
        claims.append(
            EvidenceClaim(
                run_id=run_id,
                project_id=project_id,
                meeting_id=meeting_id,
                claim_key=key,
                value_json=value,
                source_kind="fact_aggregation",
                source_priority=20,
                extraction_pass="fact_aggregation",
                evidence_text=str(
                    (facts.get("fact_evidence") or facts.get("_fact_evidence") or {}).get(key)
                    or "聚合资料事实"
                )[:1200],
                confidence=float(
                    (facts.get("fact_confidence") or facts.get("_fact_confidence") or {}).get(key) or 0.5
                ),
                status="needs_review",
            )
        )
    return claims


def _upsert_decisions(
    db: Session,
    *,
    run_id: str,
    project_id: str,
    meeting_id: str,
    claims: list[EvidenceClaim],
) -> list[FactDecision]:
    db.query(FactDecision).filter_by(run_id=run_id).delete()
    grouped: dict[str, list[EvidenceClaim]] = defaultdict(list)
    for claim in claims:
        grouped[claim.claim_key].append(claim)

    decisions: list[FactDecision] = []
    for key, options in grouped.items():
        ordered = sorted(options, key=lambda item: (item.source_priority, item.confidence), reverse=True)
        top_priority = ordered[0].source_priority
        top = [item for item in ordered if item.source_priority == top_priority]
        values = {_normal(item.value_json) for item in top}
        conflict = len(values) > 1
        selected = max(top, key=lambda item: item.confidence)
        status = "conflict" if conflict else ("accepted" if selected.confidence >= 0.55 else "needs_review")
        decisions.append(
            FactDecision(
                run_id=run_id,
                project_id=project_id,
                meeting_id=meeting_id,
                fact_key=key,
                value_json=None if conflict else selected.value_json,
                status=status,
                confidence=0.0 if conflict else selected.confidence,
                claim_ids_json=[item.id for item in ordered],
                conflict_json=[
                    {
                        "claim_id": item.id,
                        "value": item.value_json,
                        "file_id": item.file_id,
                        "page_number": item.page_number,
                        "confidence": item.confidence,
                    }
                    for item in top
                ]
                if conflict
                else None,
                source_summary_json={
                    "file_id": selected.file_id,
                    "source_kind": selected.source_kind,
                    "page_number": selected.page_number,
                    "region": selected.region_json,
                    "evidence": selected.evidence_text,
                    "priority": selected.source_priority,
                },
            )
        )
    db.add_all(decisions)
    db.commit()
    return decisions


def materialize_evidence_graph(
    db: Session,
    *,
    run_id: str,
    project_id: str,
    meeting_id: str,
    facts: dict[str, Any],
) -> list[FactDecision]:
    """Persist parser observations then arbitrate one decision per fact."""
    db.query(EvidenceClaim).filter_by(run_id=run_id).delete()
    files = {
        file.id: file
        for file in db.query(FileRecord).filter_by(project_id=project_id, meeting_id=meeting_id).all()
    }
    docs = db.query(ParsedDocument).filter_by(project_id=project_id, meeting_id=meeting_id).all()
    claims: list[EvidenceClaim] = []
    for document in docs:
        file_record = files.get(document.file_id)
        if not file_record:
            continue
        content = document.content_json or {}
        category = document.document_type or file_record.document_category or "unknown"
        evidence_text = str(content.get("text_content") or "")
        for fields, page, region, extraction_pass in _iter_field_sets(content):
            claims.extend(
                _claim_from_fields(
                    run_id=run_id,
                    project_id=project_id,
                    meeting_id=meeting_id,
                    file_record=file_record,
                    category=category,
                    fields=fields,
                    page_number=page,
                    region_id=region,
                    extraction_pass=extraction_pass,
                    evidence_text=evidence_text or str(fields.get("summary_text") or ""),
                )
            )
    claims.extend(_facts_to_claims(run_id=run_id, project_id=project_id, meeting_id=meeting_id, facts=facts))
    db.add_all(claims)
    db.flush()
    return _upsert_decisions(
        db,
        run_id=run_id,
        project_id=project_id,
        meeting_id=meeting_id,
        claims=claims,
    )


def apply_fact_decisions(facts: dict[str, Any], decisions: Iterable[FactDecision]) -> dict[str, Any]:
    result = dict(facts)
    status: dict[str, str] = {}
    citations: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        status[decision.fact_key] = decision.status
        if decision.status == "accepted" and _is_present(decision.value_json):
            result[decision.fact_key] = decision.value_json
        citations[decision.fact_key] = {
            "status": decision.status,
            "confidence": decision.confidence,
            **(decision.source_summary_json or {}),
        }
    result["_evidence_status"] = status
    result["_fact_citations"] = citations
    return result


def evidence_gate(decisions: Iterable[FactDecision], present_categories: set[str]) -> dict[str, Any]:
    by_key = {item.fact_key: item for item in decisions}
    required: set[str] = set()
    if "presentation_material" in present_categories:
        required.add("presentation_topic")
    if "observation_confirmation" in present_categories:
        required.add("observation_success")
    if {"observation_confirmation", "meeting_screenshot"} & present_categories:
        required.add("max_attendee_count")
    blocked: list[str] = []
    for key in sorted(required):
        decision = by_key.get(key)
        if not decision or decision.status in {"missing", "conflict", "needs_review"}:
            blocked.append(key)
    conflicts = sorted(item.fact_key for item in by_key.values() if item.status == "conflict")
    return {
        "blocked": bool(blocked or conflicts),
        "reason": "evidence_conflict_or_missing" if blocked or conflicts else "evidence_ready",
        "required_fact_keys": sorted(required),
        "blocked_fact_keys": sorted(set(blocked + conflicts)),
        "conflict_fact_keys": conflicts,
    }


def fact_citations(db: Session, project_id: str, meeting_id: str, *, limit: int = 12) -> list[dict[str, Any]]:
    from app.services.agent.case_run import latest_case_run

    run = latest_case_run(db, project_id, meeting_id)
    if not run:
        return []
    rows = (
        db.query(FactDecision)
        .filter_by(run_id=run.id)
        .order_by(FactDecision.updated_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "fact_key": row.fact_key,
            "value": row.value_json,
            "status": row.status,
            "confidence": row.confidence,
            "source": row.source_summary_json or {},
        }
        for row in rows
    ]
