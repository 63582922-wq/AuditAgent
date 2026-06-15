from pathlib import Path

import pytest

from app.services.domain.compliance.case_loader import import_case_folder
from app.services.domain.compliance.cross_checker import run_compliance_checks
from app.services.domain.compliance.classifier import classify_compliance_document, infer_meeting_code


FX_CASE = Path(__file__).resolve().parents[2] / "FX"


def test_classify_a1_export():
    cls = classify_compliance_document("Remote_A1P260307357_export.pdf", ".pdf", "会议编号 A1P260307357")
    assert cls["document_category"] == "a1_meeting_export"
    assert cls["confidence"] >= 0.9


def test_infer_meeting_code():
    code = infer_meeting_code(["Remote_A1P260307357_20260506.pdf", "other.xlsx"])
    assert code == "A1P260307357"


def test_import_case_folder(db, monkeypatch):
    if not FX_CASE.is_dir():
        pytest.skip("FX 样本目录不存在")

    monkeypatch.setattr("app.config.settings.agent_domain", "compliance")
    project_id, meeting_id, profile = import_case_folder(db, FX_CASE, "测试案件")
    assert profile.get("meeting_code") == "A1P260307357"
    assert project_id
    assert meeting_id


def test_compliance_rules_on_facts():
    facts = {
        "meeting_code": "A1P260307357",
        "speaker_service_minutes": 10,
        "planned_duration_minutes": 30,
        "actual_duration_minutes": 30,
        "duration_delta_minutes": 0,
        "has_confirmation": True,
        "has_a1_export": True,
        "has_coordination_sms": True,
        "material_code": "M-CN-00013658",
        "planned_attendees": 7,
        "actual_sign_in_count": 7,
        "attendance_delta": 0,
    }
    rules = [
        {
            "rule_id": "CMP-001",
            "rule_name": "付费讲者讲课时长不足15分钟",
            "risk_category": "违反公司制度",
            "risk_level": "高",
            "condition": {"all": [{"field": "speaker_service_minutes", "operator": "<", "value": 15}]},
            "evidence_fields": ["speaker_service_minutes"],
            "suggestion_template": "时长不足",
            "enabled": True,
        }
    ]
    hits = run_compliance_checks(facts, rules)
    assert len(hits) == 1
    assert hits[0]["rule_triggered"] == "CMP-001"


def test_harness_import_and_rules_only(db, monkeypatch):
    if not FX_CASE.is_dir():
        pytest.skip("FX 样本目录不存在")

    from app.services.agent.harness import ComplianceHarness

    monkeypatch.setattr("app.config.settings.agent_domain", "compliance")
    monkeypatch.setattr(
        "app.services.domain.compliance.finding_generator.generate_finding_narratives",
        lambda hits, profile, obs_type="Remote": [{**h, "analysis": h["suggestion"]} for h in hits],
    )

    harness = ComplianceHarness(db)
    project_id, meeting_id, _ = harness.import_case(FX_CASE, "Harness 测试")
    result = harness.run(project_id, meeting_id, skip_orchestrator=True)
    assert result.meeting_code == "A1P260307357"
    assert result.finding_count >= 0
    assert result.status in ("completed", "needs_review", "accepted")
