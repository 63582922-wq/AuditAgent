from __future__ import annotations

from openpyxl import Workbook

from app.services.agent.workflow import _meeting_case_patch_from_fixed_template


def test_meeting_case_patch_from_fixed_template_extracts_key_live_fields(tmp_path) -> None:
    path = tmp_path / "固定模板输出.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["分类"] * 8)
    ws.append([
        "会议编码",
        "实际会议地点（线上平台）",
        "开始时人数（不含Roche员工）",
        "会中最大人数（不含Roche员工）",
        "结束时人数（不含Roche员工）",
        "PPT主题及编码",
        "PPT页数",
        "是否问题会议\n（前面问题点选项有1的，此处填1，若无，填0）",
    ])
    ws.append([
        "SMS202606090070",
        "ZOOM",
        "15",
        "16",
        "14",
        "新剂型助力HER2阳性晚期一线高质量治愈\nP-HPK-2025.05-090 Valid Until 2027.05",
        1,
        1,
    ])
    wb.save(path)

    patch = _meeting_case_patch_from_fixed_template(path)

    assert patch["meeting_code"] == "SMS202606090070"
    assert patch["actual_platform"] == "ZOOM"
    assert patch["start_attendee_count"] == 15
    assert patch["max_attendee_count"] == 16
    assert patch["end_attendee_count"] == 14
    assert patch["presentation_topic"] == "新剂型助力HER2阳性晚期一线高质量治愈"
    assert patch["material_code"] == "P-HPK-2025.05-090"
    assert patch["ppt_pages"] == 1
    assert patch["is_problem_meeting"] == 1


def test_meeting_case_patch_from_fixed_template_keeps_composite_attendee_counts_as_template_display(tmp_path) -> None:
    path = tmp_path / "固定模板输出.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append([
        "会议编码",
        "开始时人数（不含Roche员工）",
        "会中最大人数（不含Roche员工）",
        "结束时人数（不含Roche员工）",
    ])
    ws.append(["SMS202606090070", "7+46人次", "5+61人次", "8+61人次"])
    wb.save(path)

    patch = _meeting_case_patch_from_fixed_template(path)

    assert "start_attendee_count" not in patch
    assert "max_attendee_count" not in patch
    assert "end_attendee_count" not in patch
    assert patch["template_start_attendee_count"] == "7+46人次"
    assert patch["template_max_attendee_count"] == "5+61人次"
    assert patch["template_end_attendee_count"] == "8+61人次"
