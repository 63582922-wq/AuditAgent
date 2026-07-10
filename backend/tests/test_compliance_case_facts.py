from __future__ import annotations

from types import SimpleNamespace

from app.services.domain.compliance.cross_checker import build_case_facts


def test_compliance_case_facts_reuse_template_material_facts() -> None:
    files = [
        SimpleNamespace(document_category="sign_in_record"),
        SimpleNamespace(document_category="presentation_material"),
    ]
    parsed_docs = [
        {
            "file_name": "Remote_A1P260307357_20260506_签到表 (1).jpg",
            "document_category": "sign_in_record",
            "text_content": "签到表\n辛璐 已签到\n姜越 已签到",
            "content_json": {"fields": {"vision_confidence": 0.72}},
        },
        {
            "file_name": "Remote_A1P260307357_20260506_PPT (1).jpg",
            "document_category": "presentation_material",
            "text_content": "幻灯片 1/30",
            "content_json": {
                "fields": {
                    "presentation_topic": "宝山学术交流0506",
                    "material_code": "M-CN-123456",
                    "ppt_pages": 30,
                    "vision_confidence": 0.88,
                }
            },
        },
    ]

    facts = build_case_facts(
        {
            "meeting_code": "A1P260307357",
            "observation_type": "远程观察",
            "planned_attendees": 6,
        },
        files,
        parsed_docs,
    )

    assert facts["actual_sign_in_count"] == 2
    assert facts["material_code"] == "M-CN-123456"
    assert facts["presentation_topic"] == "宝山学术交流0506"
    assert facts["ppt_pages"] == 30


def test_watch_record_is_not_treated_as_zero_sign_in_count() -> None:
    files = [SimpleNamespace(document_category="sign_in_record")]
    parsed_docs = [
        {
            "file_name": "Remote_SMS202606090070_20260615_线上直播观看数据.xlsx",
            "document_category": "sign_in_record",
            "text_content": "",
            "content_json": {
                "sheets": [
                    {
                        "sheet_name": "观看记录详情",
                        "rows": [
                            {
                                "values": {
                                    "会议时间": "2026-06-15 19:00-21:17",
                                    "观众姓名": "李*",
                                    "登录时间": "2026-06-15 18:04:47",
                                    "登录时长": "00:52:48",
                                }
                            },
                            {
                                "values": {
                                    "会议时间": "2026-06-15 19:00-21:17",
                                    "观众姓名": "张*",
                                    "登录时间": "2026-06-15 18:12:47",
                                    "登录时长": "01:10:51",
                                }
                            },
                        ],
                    }
                ]
            },
        }
    ]

    facts = build_case_facts(
        {
            "meeting_code": "SMS202606090070",
            "observation_type": "远程观察",
            "planned_attendees": 7,
            "actual_sign_in_count": 0,
        },
        files,
        parsed_docs,
    )

    assert facts["attendance_source"] == "watch_record"
    assert facts["watch_record_count"] == 2
    assert facts["actual_sign_in_count"] is None
    assert facts["attendance_delta"] is None


def test_sms_facts_keep_attendance_channels_separate() -> None:
    files = [
        SimpleNamespace(document_category="observation_confirmation"),
        SimpleNamespace(document_category="meeting_screenshot"),
        SimpleNamespace(document_category="sign_in_record"),
    ]
    parsed_docs = [
        {
            "file_name": "Remote_SMS202606090070_20260615_确认单 (1).jpg",
            "document_category": "observation_confirmation",
            "text_content": "实际会议开始人数：5 实际会议结束人数：5",
            "content_json": {
                "fields": {
                    "start_attendee_count": 5,
                    "end_attendee_count": 5,
                    "vision_confidence": 0.84,
                }
            },
        },
        {
            "file_name": "Remote_SMS202606090070_20260615_最大端口数_zoom端 (1).jpg",
            "document_category": "meeting_screenshot",
            "text_content": "参会者 (15)",
            "content_json": {
                "fields": {
                    "max_attendee_count": 15,
                    "vision_confidence": 0.88,
                }
            },
        },
        {
            "file_name": "Remote_SMS202606090070_20260615_线上截图_ZOOM端 (17).jpg",
            "document_category": "meeting_screenshot",
            "text_content": "参会者 12",
            "content_json": {
                "fields": {
                    "max_attendee_count": 12,
                    "vision_confidence": 0.86,
                }
            },
        },
        {
            "file_name": "Remote_SMS202606090070_20260615_线上直播观看数据.xlsx",
            "document_category": "sign_in_record",
            "text_content": "",
            "content_json": {
                "sheets": [
                    {
                        "sheet_name": "观看记录详情",
                        "rows": [
                            {"values": {"会议时间": "2026-06-15 19:00-21:17", "观众姓名": "李*", "登录时间": "18:04", "登录时长": "00:52:48"}},
                            {"values": {"会议时间": "2026-06-15 19:00-21:17", "观众姓名": "张*", "登录时间": "18:12", "登录时长": "01:10:51"}},
                        ],
                    }
                ]
            },
        },
    ]

    facts = build_case_facts(
        {
            "meeting_code": "SMS202606090070",
            "observation_type": "远程观察",
            "planned_attendees": 7,
        },
        files,
        parsed_docs,
    )

    assert facts["start_attendee_count"] == 5
    assert facts["end_attendee_count"] == 5
    assert facts["zoom_peak_count"] == 15
    assert facts["max_attendee_count"] == 15
    assert facts["watch_record_count"] == 2
    assert facts["total_attendance_expression"] == "5+2人次"
    assert facts["actual_sign_in_count"] is None
    assert facts["attendance_delta"] is None


def test_sms_attendance_expression_uses_confirmation_consensus_before_screenshot_count() -> None:
    files = [
        SimpleNamespace(document_category="meeting_screenshot"),
        SimpleNamespace(document_category="observation_confirmation"),
        SimpleNamespace(document_category="sign_in_record"),
    ]
    parsed_docs = [
        {
            "file_name": "Remote_SMS202606090070_20260615_确认单 (1).jpg",
            "document_category": "observation_confirmation",
            "text_content": "远程观察确认单，手写人数存在识别风险",
            "content_json": {
                "fields": {
                    "vision_manual_review_required": True,
                    "vision_review_reasons": ["handwriting_risk"],
                },
                "vision_consensus": {
                    "status": "needs_review",
                    "fields": {
                        "start_attendee_count": "5名献者A.付费主席B.付费讲者",
                        "end_attendee_count": "5名献者A.付费主席B.付费讲者",
                    },
                    "field_confidence": {
                        "start_attendee_count": 0.6,
                        "end_attendee_count": 0.6,
                    },
                },
            },
        },
        {
            "file_name": "Remote_SMS202606090070_20260615_线上截图_ZOOM端 (23).jpg",
            "document_category": "meeting_screenshot",
            "text_content": "会议截图显示当前有14位参会者",
            "content_json": {
                "fields": {
                    "start_attendee_count": 14,
                    "end_attendee_count": 14,
                    "vision_confidence": 0.95,
                }
            },
        },
        {
            "file_name": "Remote_SMS202606090070_20260615_线上直播观看数据.xlsx",
            "document_category": "sign_in_record",
            "text_content": "",
            "content_json": {
                "sheets": [
                    {
                        "sheet_name": "观看记录详情",
                        "rows": [
                            {"values": {"会议时间": "2026-06-15 19:00-21:17", "观众姓名": "李*", "登录时间": "18:04", "登录时长": "00:52:48"}},
                            {"values": {"会议时间": "2026-06-15 19:00-21:17", "观众姓名": "张*", "登录时间": "18:12", "登录时长": "01:10:51"}},
                        ],
                    }
                ]
            },
        },
    ]

    facts = build_case_facts(
        {
            "meeting_code": "SMS202606090070",
            "observation_type": "远程观察",
            "planned_attendees": 7,
        },
        files,
        parsed_docs,
    )

    assert facts["start_attendee_count"] == 5
    assert facts["end_attendee_count"] == 5
    assert facts["total_attendance_expression"] == "5+2人次"
    assert facts["fact_sources"]["start_attendee_count"].endswith("确认单 (1).jpg")


def test_sms_presentation_topic_prefers_ppt_cover_over_agenda_subtopic() -> None:
    files = [
        SimpleNamespace(document_category="presentation_material"),
        SimpleNamespace(document_category="meeting_agenda"),
        SimpleNamespace(document_category="meeting_screenshot"),
    ]
    parsed_docs = [
        {
            "file_name": "Remote_SMS202606090070_20260615_线上截图_ZOOM端 (14).jpg",
            "document_category": "meeting_screenshot",
            "text_content": "PIK3CA突变、HR+/HER2-晚期乳腺癌一线病例分享",
            "content_json": {
                "fields": {
                    "presentation_topic": "PIK3CA突变、HR+/HER2-晚期乳腺癌一线病例分享",
                    "vision_confidence": 0.92,
                }
            },
        },
        {
            "file_name": "Remote_SMS202606090070_20260615_PPT.jpg",
            "document_category": "presentation_material",
            "text_content": "标题为“新剂型-助力HER2阳性晚期一线走向高质量治愈”",
            "content_json": {
                "fields": {
                    "presentation_topic": "新剂型-助力HER2阳性晚期一线走向高质量治愈",
                    "material_code": "P-HPK-2025.05-090",
                    "ppt_pages": 30,
                    "vision_confidence": 0.86,
                },
                "field_confidence": {"presentation_topic": 0.86},
            },
        },
        {
            "file_name": "Remote_SMS202606090070_20260615_会议日程.jpg",
            "document_category": "meeting_agenda",
            "text_content": "会议日程：PIK3CA突变、HR+/HER2-晚期乳腺癌一线病例分享",
            "content_json": {"fields": {"vision_confidence": 0.9}},
        },
    ]

    facts = build_case_facts(
        {
            "meeting_code": "SMS202606090070",
            "observation_type": "远程观察",
            "planned_attendees": 7,
        },
        files,
        parsed_docs,
    )

    assert facts["presentation_topic"] == "新剂型-助力HER2阳性晚期一线走向高质量治愈"
    assert facts["material_code"] == "P-HPK-2025.05-090"
