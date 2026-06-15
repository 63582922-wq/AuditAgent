from pathlib import Path

from app.services.outputs.compliance_deliverables import build_compliance_deliverable_bundle


def test_build_compliance_deliverable_bundle(tmp_path):
    findings = [
        {
            "risk_id": "FIND-001",
            "risk_level": "高",
            "risk_score": 85,
            "risk_category": "计划不一致",
            "problem": "讲者时长超出计划",
            "rule_triggered": "CMP-001",
            "evidence_json": {"speaker_service_minutes": 45},
            "suggestion": "核实 A1 计划并补充说明",
            "manual_review_required": False,
            "status": "pending",
            "source_file_id": "file-1",
        }
    ]
    missing = [
        {"document_type": "sign_in_record", "importance": "中", "reason": "缺少签到记录"},
    ]
    materials = [
        {
            "file_id": "file-1",
            "file_name": "签到表.jpg",
            "document_category": "sign_in_record",
            "ocr_engine": "vision:glm-ocr",
            "text_content": "签到人数 12",
            "md_results": "# 签到表\n\n签到人数 12",
            "layout_details": [[{"label": "text", "content": "签到人数 12"}]],
            "layout_counts": {"text": 1, "table": 0, "image": 0, "formula": 0, "other": 0},
            "char_count": 8,
        }
    ]
    bundle = build_compliance_deliverable_bundle(
        tmp_path,
        "观察案件 TEST",
        findings,
        missing,
        meeting_case={"meeting_code": "A1PTEST001", "observation_type": "远程观察"},
        file_names={"file-1": "签到表.jpg"},
        parsed_materials=materials,
    )

    assert bundle["deliverable_package"].exists()
    assert bundle["finding_pdf"].suffix == ".pdf"
    assert bundle["finding_excel"].suffix == ".xlsx"
    assert bundle["observation_summary"].exists()
    assert bundle["evidence_index"].exists()
    assert bundle["material_parse_index"].exists()
    assert bundle["missing_docs"].exists()
    assert bundle["correction_list"].exists()
    assert (bundle["material_parse_index"].parent / "markdown").exists()
    md_files = list((bundle["material_parse_index"].parent / "markdown").glob("*.md"))
    assert md_files
    assert "RemoteObservation" in bundle["deliverable_package"].name
