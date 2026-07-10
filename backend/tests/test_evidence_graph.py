from app.models import FileRecord, Meeting, ParsedDocument, Project
from app.services.agent.case_run import create_case_run
from app.services.domain.compliance.cross_checker import run_compliance_checks
from app.services.domain.compliance.evidence_graph import (
    apply_fact_decisions,
    evidence_gate,
    materialize_evidence_graph,
)


def _case(db, code: str = "SMS-EVIDENCE"):
    project = Project(name="证据账本测试", status="active")
    db.add(project)
    db.commit()
    meeting = Meeting(project_id=project.id, meeting_code=code, status="draft", state_json={})
    db.add(meeting)
    db.commit()
    return project, meeting


def _document(db, project, meeting, *, name: str, category: str, fields: dict, confidence: float = 0.92):
    record = FileRecord(
        project_id=project.id,
        meeting_id=meeting.id,
        file_name=name,
        file_type="image",
        document_category=category,
        storage_path=f"/tmp/{name}",
        parse_status="parsed",
        confidence=confidence,
    )
    db.add(record)
    db.commit()
    db.add(
        ParsedDocument(
            project_id=project.id,
            meeting_id=meeting.id,
            file_id=record.id,
            document_type=category,
            text_content=f"{name} extracted evidence",
            content_json={"fields": fields, "field_confidence": {key: confidence for key in fields}},
        )
    )
    db.commit()
    return record


def test_presentation_fact_prefers_ppt_over_agenda(db):
    project, meeting = _case(db)
    _document(
        db,
        project,
        meeting,
        name="agenda.jpg",
        category="meeting_agenda",
        fields={"presentation_topic": "议程中的旧主题"},
    )
    _document(
        db,
        project,
        meeting,
        name="PPT.jpg",
        category="presentation_material",
        fields={"presentation_topic": "PPT封面中的实际主题", "ppt_pages": 36},
    )
    run = create_case_run(db, project.id, meeting.id)

    decisions = materialize_evidence_graph(
        db,
        run_id=run.id,
        project_id=project.id,
        meeting_id=meeting.id,
        facts={"presentation_topic": "聚合猜测"},
    )
    facts = apply_fact_decisions({}, decisions)

    assert facts["presentation_topic"] == "PPT封面中的实际主题"
    assert facts["_evidence_status"]["presentation_topic"] == "accepted"
    assert facts["_fact_citations"]["presentation_topic"]["priority"] == 100


def test_conflicting_primary_evidence_blocks_rule_and_delivery_gate(db):
    project, meeting = _case(db)
    _document(
        db,
        project,
        meeting,
        name="确认单1.jpg",
        category="observation_confirmation",
        fields={"actual_duration_minutes": 45, "observation_success": True, "max_attendee_count": 12},
    )
    _document(
        db,
        project,
        meeting,
        name="确认单2.jpg",
        category="observation_confirmation",
        fields={"actual_duration_minutes": 60, "observation_success": True, "max_attendee_count": 12},
    )
    run = create_case_run(db, project.id, meeting.id)
    decisions = materialize_evidence_graph(
        db,
        run_id=run.id,
        project_id=project.id,
        meeting_id=meeting.id,
        facts={"actual_duration_minutes": 45, "planned_duration_minutes": 30},
    )
    facts = apply_fact_decisions({"actual_duration_minutes": 45}, decisions)
    rule = {
        "rule_id": "CMP-EVIDENCE",
        "rule_name": "实际时长偏差",
        "risk_category": "计划",
        "risk_level": "低",
        "condition": {"field": "actual_duration_minutes", "operator": ">", "value": 30},
        "evidence_fields": ["actual_duration_minutes"],
        "suggestion_template": "核实实际时长",
    }

    hits, outcomes = run_compliance_checks(facts, [rule], return_outcomes=True)
    gate = evidence_gate(decisions, {"observation_confirmation"})

    assert hits == []
    assert outcomes == [
        {
            "rule_id": "CMP-EVIDENCE",
            "rule_name": "实际时长偏差",
            "status": "needs_review",
            "reason": "关键证据存在冲突、低置信或待核实状态",
            "evidence": {
                "actual_duration_minutes": 45,
                "_evidence_status": {"actual_duration_minutes": "conflict"},
            },
        }
    ]
    assert gate["blocked"] is True
    assert "actual_duration_minutes" in gate["conflict_fact_keys"]
