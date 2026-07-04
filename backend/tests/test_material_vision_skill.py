from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter

from app.services.domain.compliance.compliance_vision import (
    analyze_compliance_pil_image,
    normalize_compliance_vision,
)
from app.services.domain.compliance.material_vision_skill import (
    build_material_vision_profile,
    build_vision_consensus,
)


def test_handwritten_confirmation_requires_field_level_review() -> None:
    image = Image.new("RGB", (1600, 1100), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "现场确认单\n医生手写签名\n到场确认", fill="black")

    profile = build_material_vision_profile(
        image=image,
        document_category="observation_confirmation",
        file_name="Remote_A1P260307357_到场确认单.jpg",
        fields={
            "vision_confidence": 0.78,
            "summary_text": "现场确认单，含医生手写签名",
            "meeting_code": "",
            "speaker_service_minutes": 0,
            "observation_success": "",
        },
        raw_text="现场确认单\n医生手写签名\n到场确认",
    )

    assert profile["manual_review_required"] is True
    assert "handwriting_risk" in profile["review_reasons"]
    assert "speaker_service_minutes" in profile["recognition_plan"]["target_fields"]
    assert "field_crop_ocr" in profile["recognition_plan"]["passes"]
    assert profile["field_confidence"]["meeting_code"] < 0.7


def test_low_quality_image_for_sign_in_requires_review_even_with_text() -> None:
    image = Image.new("RGB", (420, 220), (238, 238, 238))
    draw = ImageDraw.Draw(image)
    draw.text((20, 70), "签到表 5人", fill=(165, 165, 165))
    image = image.filter(ImageFilter.GaussianBlur(radius=2.2))

    profile = build_material_vision_profile(
        image=image,
        document_category="sign_in_record",
        file_name="sign-in.png",
        fields={"vision_confidence": 0.86, "actual_sign_in_count": 5},
        raw_text="签到表 5人",
    )

    assert profile["manual_review_required"] is True
    assert "low_resolution" in profile["review_reasons"]
    assert "low_contrast" in profile["review_reasons"]
    assert profile["quality"]["score"] < 0.75
    assert "image_enhancement" in profile["recognition_plan"]["passes"]


def test_long_screenshot_requires_slicing_plan() -> None:
    image = Image.new("RGB", (1276, 12779), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 80), "沟通短信 长截图", fill="black")

    profile = build_material_vision_profile(
        image=image,
        document_category="coordination_sms",
        file_name="沟通短信 (1).jpg",
        fields={"vision_confidence": 0.92, "key_facts": ["会议时间沟通"]},
        raw_text="沟通短信 长截图",
    )

    assert profile["manual_review_required"] is True
    assert "long_image_needs_slicing" in profile["review_reasons"]
    assert "long_image_slicing" in profile["recognition_plan"]["passes"]


def test_clear_meeting_screenshot_can_auto_continue_when_confident() -> None:
    image = Image.new("RGB", (1800, 1200), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 100, 1700, 1000), outline="black", width=6)
    draw.text((160, 180), "会议截图\n讲者: Amy Luo\n时长: 45分钟", fill="black")

    profile = build_material_vision_profile(
        image=image,
        document_category="meeting_screenshot",
        file_name="meeting.png",
        fields={
            "vision_confidence": 0.93,
            "speaker_name": "Amy Luo",
            "actual_duration_minutes": 45,
        },
        raw_text="会议截图\n讲者 Amy Luo\n时长 45分钟",
    )

    assert profile["manual_review_required"] is False
    assert profile["quality"]["score"] >= 0.75
    assert profile["recognition_plan"]["strategy"] == "standard_vision_ocr"


def test_sign_in_consensus_accepts_agreed_field_values() -> None:
    consensus = build_vision_consensus(
        document_category="sign_in_record",
        candidates=[
            {
                "pass_id": "layout_ocr",
                "fields": {"actual_sign_in_count": 6, "meeting_code": "A1P260307357"},
                "field_confidence": {"actual_sign_in_count": 0.91, "meeting_code": 0.88},
            },
            {
                "pass_id": "handwriting_focused_pass",
                "fields": {"actual_sign_in_count": 6, "meeting_code": "A1P260307357"},
                "field_confidence": {"actual_sign_in_count": 0.86, "meeting_code": 0.83},
            },
        ],
    )

    assert consensus["status"] == "accepted"
    assert consensus["manual_review_required"] is False
    assert consensus["fields"]["actual_sign_in_count"] == 6
    assert consensus["field_confidence"]["actual_sign_in_count"] == 0.86
    assert consensus["conflicts"] == []


def test_sign_in_consensus_flags_conflicting_count_for_manual_review() -> None:
    consensus = build_vision_consensus(
        document_category="sign_in_record",
        candidates=[
            {
                "pass_id": "layout_ocr",
                "fields": {"actual_sign_in_count": 5},
                "field_confidence": {"actual_sign_in_count": 0.89},
            },
            {
                "pass_id": "handwriting_focused_pass",
                "fields": {"actual_sign_in_count": 6},
                "field_confidence": {"actual_sign_in_count": 0.84},
            },
        ],
    )

    assert consensus["status"] == "needs_review"
    assert consensus["manual_review_required"] is True
    assert "vision_consensus_conflict" in consensus["review_reasons"]
    assert consensus["fields"]["actual_sign_in_count"] is None
    assert consensus["field_confidence"]["actual_sign_in_count"] <= 0.45
    assert consensus["conflicts"] == [
        {
            "field": "actual_sign_in_count",
            "values": [
                {"pass_id": "layout_ocr", "value": 5, "confidence": 0.89},
                {"pass_id": "handwriting_focused_pass", "value": 6, "confidence": 0.84},
            ],
        }
    ]


def test_compliance_pil_analysis_includes_vision_reliability_gate(monkeypatch) -> None:
    image = Image.new("RGB", (420, 220), (238, 238, 238))
    draw = ImageDraw.Draw(image)
    draw.text((20, 70), "现场确认单 医生手写签名", fill=(165, 165, 165))
    image = image.filter(ImageFilter.GaussianBlur(radius=2.2))

    monkeypatch.setattr("app.services.vision_client.vision_available", lambda: True)

    def fake_vision_analyze(*args, **kwargs):
        return {
            "_model": "test-vision",
            "summary_text": "现场确认单 医生手写签名",
            "reasoning": "识别到到场确认信息，但关键字段缺失",
            "confidence": 0.76,
            "meeting_code": "",
            "speaker_service_minutes": 0,
            "observation_success": "",
        }

    monkeypatch.setattr("app.services.vision_client.vision_analyze_pil_image", fake_vision_analyze)

    content = analyze_compliance_pil_image(
        image,
        "observation_confirmation",
        "到场确认单.png",
    )

    assert content["manual_review_required"] is True
    assert "vision_quality" in content
    assert "recognition_plan" in content
    assert "field_confidence" in content
    assert "handwriting_risk" in content["review_reasons"]
    assert content["fields"]["vision_manual_review_required"] is True


def test_compliance_pil_analysis_attaches_single_pass_consensus_gate(monkeypatch) -> None:
    image = Image.new("RGB", (1600, 1100), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "签到表 已签到 6 人", fill="black")

    monkeypatch.setattr("app.services.vision_client.vision_available", lambda: True)
    monkeypatch.setattr("app.services.domain.compliance.compliance_vision.settings.vision_high_risk_min_passes", 1, raising=False)

    def fake_vision_analyze(*args, **kwargs):
        return {
            "_model": "test-vision",
            "summary_text": "签到表，已签到 6 人",
            "reasoning": "识别到签到人数",
            "confidence": 0.91,
            "actual_sign_in_count": 6,
            "meeting_code": "A1P260307357",
        }

    monkeypatch.setattr("app.services.vision_client.vision_analyze_pil_image", fake_vision_analyze)

    content = analyze_compliance_pil_image(
        image,
        "sign_in_record",
        "Remote_A1P260307357_签到表 (1).jpg",
    )

    assert content["vision_consensus"]["candidate_count"] == 1
    assert content["vision_consensus"]["status"] == "needs_review"
    assert "single_pass_high_risk_document" in content["vision_consensus"]["review_reasons"]
    assert content["fields"]["vision_consensus_status"] == "needs_review"
    assert content["fields"]["actual_sign_in_count"] == 6


def test_high_risk_sign_in_runs_second_vision_pass_for_consensus(monkeypatch) -> None:
    image = Image.new("RGB", (1600, 1100), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "签到表 已签到 6 人", fill="black")

    monkeypatch.setattr("app.services.vision_client.vision_available", lambda: True)
    monkeypatch.setattr("app.services.domain.compliance.compliance_vision.settings.vision_high_risk_min_passes", 2, raising=False)
    calls = []

    def fake_vision_analyze(*args, **kwargs):
        calls.append(kwargs.get("prompt") or (args[1] if len(args) > 1 else ""))
        return {
            "_model": "test-vision",
            "summary_text": "签到表，已签到 6 人",
            "reasoning": "识别到签到人数",
            "confidence": 0.9,
            "actual_sign_in_count": 6,
            "meeting_code": "A1P260307357",
        }

    monkeypatch.setattr("app.services.vision_client.vision_analyze_pil_image", fake_vision_analyze)

    content = analyze_compliance_pil_image(
        image,
        "sign_in_record",
        "Remote_A1P260307357_签到表 (1).jpg",
    )

    assert len(calls) == 2
    assert "独立复核" in calls[1]
    assert content["vision_consensus"]["candidate_count"] == 2
    assert content["vision_consensus"]["status"] == "accepted"
    assert content["vision_consensus"]["fields"]["actual_sign_in_count"] == 6


def test_compliance_vision_normalization_keeps_audit_specific_fields() -> None:
    fields = normalize_compliance_vision(
        {
            "summary_text": "PPT 和线上会议截图",
            "confidence": 0.9,
            "material_code": "P-HPK-2025.05-090 Valid Until 2027.05",
            "presentation_topic": "新剂型-助力HER2阳性晚期一线走向高质量治愈",
            "ppt_pages": 30,
            "actual_platform": "ZOOM 95496290261",
            "start_attendee_count": "7+46人次",
            "max_attendee_count": "5+61人次",
            "end_attendee_count": "8+61人次",
            "actual_sponsor": "中国医学基金会",
            "other_company_seen": "是",
            "other_company_name": "诺华",
        },
        "meeting_screenshot",
    )

    assert fields["ppt_pages"] == 30
    assert fields["presentation_topic"].startswith("新剂型")
    assert fields["actual_platform"] == "ZOOM 95496290261"
    assert fields["max_attendee_count"] == "5+61人次"
    assert fields["actual_sponsor"] == "中国医学基金会"
    assert fields["other_company_seen"] == "是"


def test_compliance_vision_rejects_meeting_code_as_material_code() -> None:
    fields = normalize_compliance_vision(
        {
            "summary_text": "PPT截图",
            "confidence": 0.82,
            "material_code": "SMS202606090070",
            "meeting_code": "SMS202606090070",
        },
        "presentation_material",
    )

    assert fields["meeting_code"] == "SMS202606090070"
    assert "material_code" not in fields


def test_compliance_vision_falls_back_to_valid_material_code_in_text() -> None:
    fields = normalize_compliance_vision(
        {
            "summary_text": "PPT截图 P-HPK-2025.05-090 Valid Until 2027.05",
            "confidence": 0.82,
            "material_code": "SMS202606090070",
            "meeting_code": "SMS202606090070",
        },
        "presentation_material",
    )

    assert fields["material_code"] == "P-HPK-2025.05-090"


def test_presentation_material_runs_crop_recovery_when_material_code_missing(monkeypatch) -> None:
    image = Image.new("RGB", (1200, 1800), "white")
    draw = ImageDraw.Draw(image)
    draw.text((120, 780), "PPT title", fill="black")
    draw.text((180, 1260), "P-HPK-2025.05-090 Valid Until 2027.05", fill="black")

    monkeypatch.setattr("app.services.vision_client.vision_available", lambda: True)

    calls = []

    def fake_vision_analyze_pil_image(img, *args, **kwargs):
        calls.append(img.size)
        if len(calls) == 1:
            return {
                "_model": "test-vision",
                "summary_text": "新剂型 PPT，未识别页脚编码",
                "presentation_topic": "新剂型",
                "confidence": 0.86,
            }
        return {
            "_model": "test-vision",
            "summary_text": "页脚编码 P-HPK-2025.05-090 Valid Until 2027.05",
            "material_code": "P-HPK-2025.05-090",
            "confidence": 0.92,
        }

    monkeypatch.setattr("app.services.vision_client.vision_analyze_pil_image", fake_vision_analyze_pil_image)

    content = analyze_compliance_pil_image(
        image,
        "presentation_material",
        "Remote_SMS202606090070_20260615_PPT.jpg",
    )

    assert content["fields"]["material_code"] == "P-HPK-2025.05-090"
    assert len(calls) >= 2
    assert calls[1][0] > calls[0][0]
    assert content["fields"]["vision_crop_recovery"][0]["field"] == "material_code"


def test_presentation_material_runs_crop_recovery_when_ppt_pages_are_current_slide(monkeypatch) -> None:
    image = Image.new("RGB", (936, 2025), "white")
    draw = ImageDraw.Draw(image)
    draw.text((25, 1245), "幻灯片 1 / 30", fill="black")
    draw.text((220, 920), "新剂型-助力HER2阳性晚期一线走向高质量治愈", fill="black")

    monkeypatch.setattr("app.services.vision_client.vision_available", lambda: True)

    calls = []

    def fake_vision_analyze_pil_image(img, *args, **kwargs):
        calls.append(img.size)
        if len(calls) == 1:
            return {
                "_model": "test-vision",
                "summary_text": "PPT首页",
                "presentation_topic": "新剂型动力HER2阳性晚期一线高质量治愈",
                "material_code": "P-HPK-2025.05-090",
                "ppt_pages": 1,
                "confidence": 0.72,
            }
        return {
            "_model": "test-vision",
            "summary_text": "幻灯片 1/30",
            "ppt_pages": 30,
            "confidence": 0.93,
        }

    monkeypatch.setattr("app.services.vision_client.vision_analyze_pil_image", fake_vision_analyze_pil_image)

    content = analyze_compliance_pil_image(
        image,
        "presentation_material",
        "Remote_SMS202606090070_20260615_PPT.jpg",
    )

    assert content["fields"]["material_code"] == "P-HPK-2025.05-090"
    assert content["fields"]["ppt_pages"] == 30
    assert len(calls) >= 2
    assert any(item["field"] == "ppt_pages" for item in content["fields"]["vision_crop_recovery"])
