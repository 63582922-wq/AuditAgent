from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from app.services.domain.compliance.classifier import classify_compliance_document
from app.services.domain.compliance.classifier import reclassify_vision_from_text


def _cat(file_name: str, ext: str = ".jpg") -> str:
    return classify_compliance_document(file_name, ext)["document_category"]


def _classification(file_name: str, ext: str = ".jpg") -> dict:
    return classify_compliance_document(file_name, ext)


def test_a1_case_code_prefix_does_not_override_specific_image_types() -> None:
    prefix = "Remote_A1P260307357_20260506"

    assert _cat(f"{prefix}_现场确认单 (1).jpg") == "observation_confirmation"
    assert _cat(f"{prefix}_签到表 (1).jpg") == "sign_in_record"
    assert _cat(f"{prefix}_线上截图 (1).jpg") == "meeting_screenshot"
    assert _cat(f"{prefix}_PPT (1).jpg") == "presentation_material"
    assert _cat(f"{prefix}_议程.jpg") == "meeting_agenda"
    assert _cat(f"{prefix}_讲者网络资料.png", ".png") == "speaker_profile"

    for name in [
        f"{prefix}_现场确认单 (1).jpg",
        f"{prefix}_签到表 (1).jpg",
        f"{prefix}_线上截图 (1).jpg",
        f"{prefix}_PPT (1).jpg",
        f"{prefix}_议程.jpg",
        f"{prefix}_讲者网络资料.png",
    ]:
        assert _classification(name, ".png" if name.endswith(".png") else ".jpg")["confidence"] >= 0.75


def test_actual_a1_export_still_classifies_as_a1() -> None:
    assert _cat("A1P260307357.pdf", ".pdf") == "a1_meeting_export"


def test_sms_case_supporting_material_names_are_not_lost() -> None:
    prefix = "Remote_SMS202606090070_20260615"

    assert _cat(f"{prefix}_确认单 (1).jpg") == "observation_confirmation"
    assert _cat(f"{prefix}_线上直播观看数据.xlsx", ".xlsx") == "sign_in_record"
    assert _cat(f"{prefix}_日程更新报备邮件.jpg") == "coordination_sms"
    assert _cat(f"{prefix}_最大端口数_zoom端 (1).jpg") == "meeting_screenshot"
    assert _cat(f"{prefix}_其他厂家.jpg") == "other_supporting_evidence"
    assert _cat(f"{prefix}_赞助回报_专题会.jpg") == "other_supporting_evidence"

    for name, ext in [
        (f"{prefix}_确认单 (1).jpg", ".jpg"),
        (f"{prefix}_线上直播观看数据.xlsx", ".xlsx"),
        (f"{prefix}_日程更新报备邮件.jpg", ".jpg"),
        (f"{prefix}_最大端口数_zoom端 (1).jpg", ".jpg"),
        (f"{prefix}_其他厂家.jpg", ".jpg"),
        (f"{prefix}_赞助回报_专题会.jpg", ".jpg"),
    ]:
        assert _classification(name, ext)["confidence"] >= 0.75


def test_actual_fx_supporting_folder_category_distribution() -> None:
    fx_root = Path(__file__).resolve().parents[2] / "FX"
    cases = {
        "Remote_A1P260307357_20260506_Luo, Amy Yun_Supporting": {
            "a1_meeting_export": 1,
            "sign_in_record": 3,
            "observation_confirmation": 3,
            "presentation_material": 2,
            "meeting_agenda": 1,
            "speaker_profile": 1,
        },
        "Remote_SMS202606090070_20260615_Lei, Lily Yuli_Supporting": {
            "sign_in_record": 1,
            "observation_confirmation": 3,
            "presentation_material": 1,
            "meeting_agenda": 1,
            "speaker_profile": 1,
            "other_supporting_evidence": 2,
        },
    }
    if not fx_root.exists():
        pytest.skip("FX 样本目录不存在")

    for folder_name, expected_minimums in cases.items():
        folder = fx_root / folder_name
        if not folder.exists():
            pytest.skip(f"FX 样本目录不存在: {folder_name}")
        counts = Counter(
            classify_compliance_document(path.name, path.suffix.lower())["document_category"]
            for path in folder.iterdir()
            if path.is_file() and not path.name.startswith(".")
        )
        for category, expected in expected_minimums.items():
            assert counts[category] >= expected, f"{folder_name} {category}: {counts}"


def test_vision_ocr_text_can_reclassify_ambiguous_image_name() -> None:
    result = reclassify_vision_from_text(
        file_name="image001.jpg",
        ext=".jpg",
        current_category="meeting_screenshot",
        current_confidence=0.4,
        text="现场确认单\\n本场会议是否成功观察：是\\n共计 45 分钟",
    )

    assert result is not None
    assert result["document_category"] == "observation_confirmation"
    assert result["confidence"] >= 0.75


def test_sms_confirmation_checklist_ocr_does_not_reclassify_to_a1_export() -> None:
    result = reclassify_vision_from_text(
        file_name="Remote_SMS202606090070_20260615_确认单 (3).jpg",
        ext=".jpg",
        current_category="observation_confirmation",
        current_confidence=0.85,
        text=(
            "罗氏赞助会/惠敦会议记录确认书\n"
            "会议编号 SMS202606090070\n"
            "会议合规检查表，内容涵盖参会人身份、观察成功与否、违反制度及其他风险。"
        ),
    )

    assert result is None


def test_confirmation_image_filename_overrides_generic_meeting_number_text() -> None:
    result = classify_compliance_document(
        "Remote_SMS202606090070_20260615_确认单 (3).jpg",
        ".jpg",
        "会议编号 SMS202606090070\n会议合规远程观察确认单\n检查项均为 X/Y",
    )

    assert result["document_category"] == "observation_confirmation"
    assert result["confidence"] >= 0.9
