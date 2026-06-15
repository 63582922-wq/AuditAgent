from __future__ import annotations

CATEGORY_KEYWORDS = {
    "meeting_metadata": ["观察", "会议编码", "surprise", "远程观察", "a1p"],
    "finding_template": ["finding", "发现点", "roche-finding"],
    "a1_meeting_export": ["a1p", "会议编号", "a1 platform"],
    "meeting_agenda": ["议程", "agenda", "会议日程"],
    "sign_in_record": ["签到", "签到表", "签到列表"],
    "observation_confirmation": ["现场确认", "观察记录", "确认书"],
    "coordination_sms": ["沟通短信", "短信", "spcheck", "远程观察"],
    "meeting_screenshot": ["线上截图", "screenshot", "会议平台"],
    "presentation_material": ["ppt", "演讲", "文稿"],
    "speaker_profile": ["讲者", "网络资料", "医生主页"],
}

REQUIRED_EVIDENCE = [
    ("meeting_metadata", "高", "缺少观察元数据，无法确认观察类型与会议编码。"),
    ("a1_meeting_export", "高", "缺少 A1 会议系统导出，无法核对计划信息。"),
    ("observation_confirmation", "高", "缺少现场确认单，无法完成观察结论。"),
    ("sign_in_record", "中", "缺少签到记录，无法核实参会人。"),
    ("meeting_agenda", "中", "缺少会议议程，无法核对计划时长。"),
    ("coordination_sms", "低", "缺少远程观察沟通记录。"),
    ("meeting_screenshot", "中", "缺少线上会议截图。"),
    ("presentation_material", "中", "缺少演讲材料截图。"),
    ("speaker_profile", "低", "缺少讲者公开资料用于身份核验。"),
]

DOMAIN_LABEL = "会议合规远程观察"
DELIVERABLE_TYPES = [
    "finding_excel",
    "finding_pdf",
    "observation_summary",
    "evidence_index",
    "missing_docs",
    "correction_list",
    "deliverable_package",
]

DOCUMENT_CATEGORY_LABELS = {
    "meeting_metadata": "观察元数据",
    "finding_template": "Finding 模板",
    "a1_meeting_export": "A1 会议导出",
    "meeting_agenda": "会议议程",
    "sign_in_record": "签到记录",
    "observation_confirmation": "现场确认单",
    "coordination_sms": "沟通短信",
    "meeting_screenshot": "线上截图",
    "presentation_material": "演讲材料",
    "speaker_profile": "讲者资料",
    "unknown": "未识别",
}
