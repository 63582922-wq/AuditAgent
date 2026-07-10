from __future__ import annotations

from app.models import FileRecord, Meeting, Project
from app.services.agent.pipeline_executor import PipelineExecutor
from app.services.agent.planner import _missing_from_files, _normalize_plan_for_context
from app.services.cross_checker import check_missing_documents


def test_planner_missing_docs_does_not_require_a1_for_sms_meeting(db, monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "agent_domain", "compliance")

    project = Project(name="SMS planner missing", status="created")
    db.add(project)
    db.commit()

    meeting = Meeting(
        project_id=project.id,
        meeting_code="SMS202606090070",
        observation_type="远程观察",
        status="draft",
    )
    db.add(meeting)
    db.commit()

    file_record = FileRecord(
        project_id=project.id,
        meeting_id=meeting.id,
        file_name="Remote_SMS202606090070_20260615_线上直播观看数据.xlsx",
        file_type="excel",
        document_category="sign_in_record",
        storage_path="/tmp/Remote_SMS202606090070_20260615_线上直播观看数据.xlsx",
        parse_status="uploaded",
    )
    db.add(file_record)
    db.commit()

    missing = _missing_from_files(db, project.id, [file_record])
    missing_types = {item["document_type"] for item in missing}

    assert "a1_meeting_export" not in missing_types
    assert "meeting_metadata" not in missing_types


def test_compliance_missing_docs_accepts_alternative_meeting_reality_evidence(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "agent_domain", "compliance")

    missing = check_missing_documents(
        {"a1_meeting_export", "observation_confirmation", "coordination_sms", "sign_in_record", "meeting_agenda", "presentation_material", "speaker_profile"},
        domain="compliance",
        meeting_case={"meeting_code": "A1P260307357", "observation_type": "远程观察"},
    )
    missing_types = {item["document_type"] for item in missing}

    assert "meeting_screenshot" not in missing_types


def test_pipeline_executor_missing_docs_uses_meeting_case_for_sms(db, monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "agent_domain", "compliance")
    project = Project(name="SMS pipeline missing", status="created")
    db.add(project)
    db.commit()
    meeting = Meeting(
        project_id=project.id,
        meeting_code="SMS202606090070",
        observation_type="远程观察",
        status="draft",
        state_json={"meeting_case": {"meeting_code": "SMS202606090070", "observation_type": "远程观察"}},
    )
    db.add(meeting)
    db.commit()

    executor = PipelineExecutor(db, project.id, meeting_id=meeting.id)
    missing = executor._missing_documents_for_present({"sign_in_record"})
    missing_types = {item["document_type"] for item in missing}

    assert "a1_meeting_export" not in missing_types
    assert "meeting_metadata" not in missing_types


def test_planner_normalizes_sms_plan_that_claims_a1_missing(db, monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "agent_domain", "compliance")
    project = Project(name="SMS normalize", status="created")
    db.add(project)
    db.commit()
    meeting = Meeting(
        project_id=project.id,
        meeting_code="SMS202606090070",
        observation_type="远程观察",
        status="draft",
        state_json={"meeting_case": {"meeting_code": "SMS202606090070", "observation_type": "远程观察"}},
    )
    db.add(meeting)
    db.commit()
    file_record = FileRecord(
        project_id=project.id,
        meeting_id=meeting.id,
        file_name="Remote_SMS202606090070_20260615_线上直播观看数据.xlsx",
        file_type="excel",
        document_category="sign_in_record",
        storage_path="/tmp/Remote_SMS202606090070_20260615_线上直播观看数据.xlsx",
        parse_status="uploaded",
    )
    db.add(file_record)
    db.commit()

    plan = {
        "missing_documents": [
            {"doc_type": "a1_meeting_export", "importance": "高", "impact": "严重缺失"},
            {"document_type": "meeting_metadata", "importance": "高", "impact": "缺失"},
        ],
        "focus_areas": ["A1会议系统导出缺失，属于严重合规缺陷", "签到数据真实性"],
        "priority_actions": ["立即标记A1缺失为最高风险项", "核对直播观看数据"],
        "reasoning": "历史记忆显示 SMS202606090070 has_a1_export=false，因此A1缺失是严重问题。",
    }

    normalized = _normalize_plan_for_context(db, project.id, [file_record], plan)
    missing_types = {
        item.get("document_type") or item.get("doc_type")
        for item in normalized["missing_documents"]
    }

    assert "a1_meeting_export" not in missing_types
    assert "meeting_metadata" not in missing_types
    assert normalized["focus_areas"] == ["签到数据真实性", "SMS远程观察替代证据链核对"]
    assert normalized["priority_actions"] == ["核对直播观看数据", "按SMS远程观察口径核对直播观看数据、确认单、ZOOM/直播截图与沟通记录"]
    assert "A1缺失" not in normalized["reasoning"]
    assert "不要求A1导出" in normalized["reasoning"]
