from __future__ import annotations

from app.services.domain.compliance.template_field_engine import build_fixed_template_field_results
from app.services.outputs.template_quality import evaluate_template_field_results


def _values_by_header(results):
    return {item.header: item.value for item in results}


def test_a1p_text_materials_populate_fixed_template_fields() -> None:
    headers = [
        "会议类型",
        "申请人姓名",
        "计划组织者姓名",
        "PR号码\n(Simplebuy)",
        "BU",
        "会议计划日期",
        "计划开始时间",
        "计划参会人数（不包含罗氏员工）",
        "计划参会罗氏员工",
        "产品名称",
        "省份",
        "城市",
        "会议地点类型",
        "实际会议地点（线上平台）",
        "所有讲者姓名\n（请在括号中填写是否付费或罗氏员工）",
        "本场会议是否有付费讲者和付费主席",
        "实际付费讲者人数",
        "实际付费主席人数",
        "讲者和主席演讲时长（分钟）",
        "主题",
    ]
    pdf_text = """
会议编号：A1P260307357
会议日期：2026-05-06 至 2026-05-06
会议城市：上海市
会议人数：总人数：7(内部人数：1 外部人数：6 ）
会议申请人：张闯（17717389425, chuang.zhang.cz1@roche.com）
会议组织者：张闯（17717389425,chuang.zhang.cz1@roche.com）
组织者部门：Customer Engagement - Ophthalmology and Neuroscience (CE-ON)
直 线 经 理：朱志伟（13072109989, zhiwei.zhu.zz1@roche.com）
会议类型：区域会
院内/院外：院外
是否网络会议：线上
产品：罗视佳
讲者级别： 国家级1人
讲者/主席姓名
讲者身份
讲者级别
黄洁
临床医生
国家级
讲者
演讲时长
分钟
30
"""
    agenda_text = """
日期：2026-05-06
时间：18:00-18:30（30分钟）
主题：宝山学术交流0506
地点：线上
"""
    materials = [
        {"file_name": "A1P260307357.pdf", "document_category": "a1_meeting_export", "text_content": pdf_text},
        {"file_name": "Remote_A1P260307357_议程.jpg", "document_category": "meeting_agenda", "text_content": agenda_text},
        {
            "file_name": "Remote_A1P260307357_现场确认单.jpg",
            "document_category": "observation_confirmation",
            "fields": {
                "actual_platform": "未知",
                "actual_date": "2026-05-06",
                "actual_start_time": "18:00",
                "actual_end_time": "18:36",
                "speaker_name": "讲者身份",
            },
            "text_content": "实际会议 2026-05-06 18:00-18:36 线上",
        },
    ]

    results = build_fixed_template_field_results(
        headers,
        {"meeting_code": "A1P260307357", "observation_type": "远程观察"},
        [],
        [],
        materials,
    )
    values = _values_by_header(results)

    assert values["会议类型"] == "区域会"
    assert values["申请人姓名"] == "张闯"
    assert values["计划组织者姓名"] == "张闯"
    assert values["PR号码\n(Simplebuy)"] == "N/A"
    assert values["BU"] == "Customer Engagement - Ophthalmology and Neuroscience (CE-ON)"
    assert str(values["会议计划日期"]) == "2026-05-06"
    assert values["计划开始时间"] == "18:00"
    assert values["计划参会人数（不包含罗氏员工）"] == 6
    assert values["计划参会罗氏员工"] == 1
    assert values["产品名称"] == "罗视佳"
    assert values["省份"] == "上海市"
    assert values["城市"] == "上海市"
    assert values["会议地点类型"] == "院外"
    assert values["实际会议地点（线上平台）"] == "线上平台"
    assert values["所有讲者姓名\n（请在括号中填写是否付费或罗氏员工）"] == "黄洁"
    assert values["本场会议是否有付费讲者和付费主席"] == "是"
    assert values["实际付费讲者人数"] == 1
    assert values["实际付费主席人数"] == 0
    assert values["讲者和主席演讲时长（分钟）"] == 30
    assert values["主题"] == "宝山学术交流0506"


def test_remote_a1p_template_uses_electronic_sign_in_count() -> None:
    headers = [
        "签到表类型（电子/纸质/电子+纸质/无签到表）",
        "签到人数（不含Roche员工）",
        "存在代签\n(是/否/远程填写无法判断）",
        "存在未参会人员签到 (是/否/远程填写无法判断）",
    ]
    materials = [
        {
            "file_name": "Remote_A1P260307357_20260506_签到表 (1).jpg",
            "document_category": "sign_in_record",
            "fields": {"actual_sign_in_count": 3, "vision_confidence": 0.95},
            "text_content": "辛璐 已签到 姜越 已签到 刘雨松 已签到",
        },
        {
            "file_name": "Remote_A1P260307357_20260506_签到表 (2).jpg",
            "document_category": "sign_in_record",
            "fields": {"actual_sign_in_count": 3, "vision_confidence": 0.85},
            "text_content": "黄洁 已签到 严嘉丽 已签到 徐春华 已签到",
        },
    ]

    results = build_fixed_template_field_results(
        headers,
        {
            "meeting_code": "A1P260307357",
            "observation_type": "远程观察",
            "actual_sign_in_count": 6,
        },
        [],
        [],
        materials,
    )
    values = _values_by_header(results)

    assert values["签到表类型（电子/纸质/电子+纸质/无签到表）"] == "电子"
    assert values["签到人数（不含Roche员工）"] == 6
    assert values["存在代签\n(是/否/远程填写无法判断）"] == "远程填写无法判断"
    assert values["存在未参会人员签到 (是/否/远程填写无法判断）"] == "远程填写无法判断"


def test_remote_a1p_template_derives_sign_in_count_from_ocr_text() -> None:
    headers = [
        "签到表类型（电子/纸质/电子+纸质/无签到表）",
        "签到人数（不含Roche员工）",
    ]
    materials = [
        {
            "file_name": "Remote_A1P260307357_20260506_签到表 (1).jpg",
            "document_category": "sign_in_record",
            "fields": {"vision_confidence": 0.72},
            "text_content": "签到表\n辛璐 已签到\n姜越 已签到\n刘雨松 已签到",
        },
        {
            "file_name": "Remote_A1P260307357_20260506_签到表 (2).jpg",
            "document_category": "sign_in_record",
            "text_content": "签到记录\n黄洁 已签到\n严嘉丽 已签到\n徐春华 已签到",
        },
    ]

    results = build_fixed_template_field_results(
        headers,
        {
            "meeting_code": "A1P260307357",
            "observation_type": "远程观察",
        },
        [],
        [],
        materials,
    )
    values = _values_by_header(results)

    assert values["签到表类型（电子/纸质/电子+纸质/无签到表）"] == "电子"
    assert values["签到人数（不含Roche员工）"] == 6


def test_remote_a1p_template_classifies_operational_and_manual_fields() -> None:
    headers = [
        "会议组织者配合程度",
        "计划组织者登陆账号",
        "计划预算金额（餐费）",
        "计划预算金额（场租）",
        "计划预算金额（设备租赁）",
        "计划预算金额（包车）",
        "计划预算金额（住宿）",
        "计划预算金额（其他____）",
        "实际组织者登陆账号",
        "本场会议是否有付费讲者和付费主席",
        "讲者和主席演讲开始时间",
        "讲者和主席演讲结束时间",
        "讲者和主席讨论时长（分钟）",
        "是否有主席/讲者照片（网络/医院公示单等）\n（均有/部分有/均无/无法判断/无主席/讲者，填写N/A）",
        "有可疑讲者\n(是/否/无法判断/观察受限/远程填写N/A）",
        "现场Roche员工",
        "有可疑参会人员\n(是/否/无法判断）",
        "现场Roche员工人数",
        "现场确认单发送日期\n（PMO根据活动反馈邮件的日期填写）",
        "备注\n（确认书写清楚）\n参考模板",
        "暗访会议备注",
        "累计计数",
        "Level9",
    ]
    a1_text = """
会议编号：A1P260307357
会议申请人：张闯（17717389425, chuang.zhang.cz1@roche.com）
会议组织者：张闯（17717389425,chuang.zhang.cz1@roche.com）
组织者部门：Customer Engagement - Ophthalmology and Neuroscience (CE-ON)
项目类型
预算金额(元)
讲课费
3000
视频会议
300
计划会议预算（含讲课费）：￥3300.00
会议总预算（不含讲课费）：￥300.00
会议总预算（含讲课费）：￥3300.00
讲者级别： 国家级1人
"""
    agenda_text = """
日期：2026-05-06
时间：18:00-18:30（30分钟）
主题：宝山学术交流0506
地点：线上
"""
    materials = [
        {"file_name": "A1P260307357.pdf", "document_category": "a1_meeting_export", "text_content": a1_text},
        {"file_name": "Remote_A1P260307357_议程.jpg", "document_category": "meeting_agenda", "text_content": agenda_text},
        {"file_name": "Remote_A1P260307357_现场确认单.jpg", "document_category": "observation_confirmation", "text_content": "现场确认单填写清楚，实际会议已完成"},
        {"file_name": "Remote_A1P260307357_讲者网络资料.png", "document_category": "speaker_profile", "text_content": "黄洁 上海市宝山区中西医结合医院 综合眼科"},
    ]

    results = build_fixed_template_field_results(
        headers,
        {
            "meeting_code": "A1P260307357",
            "observation_type": "远程观察",
            "observation_success": "是",
            "missing_documents": [],
        },
        [],
        [],
        materials,
    )
    values = _values_by_header(results)
    statuses = {item.header: item.status for item in results}
    report = evaluate_template_field_results(results)

    assert values["会议组织者配合程度"] == "配合"
    assert statuses["计划组织者登陆账号"] == "manual_required"
    assert values["计划预算金额（餐费）"] == "N/A"
    assert values["计划预算金额（场租）"] == "N/A"
    assert values["计划预算金额（设备租赁）"] == "N/A"
    assert values["计划预算金额（包车）"] == "N/A"
    assert values["计划预算金额（住宿）"] == "N/A"
    assert values["计划预算金额（其他____）"] == "300（视频会议）"
    assert statuses["实际组织者登陆账号"] == "manual_required"
    assert values["本场会议是否有付费讲者和付费主席"] == "是"
    assert values["讲者和主席演讲开始时间"] == "18:00"
    assert values["讲者和主席演讲结束时间"] == "18:30"
    assert values["讲者和主席讨论时长（分钟）"] == "N/A"
    assert values["是否有主席/讲者照片（网络/医院公示单等）\n（均有/部分有/均无/无法判断/无主席/讲者，填写N/A）"] == "均有"
    assert values["有可疑讲者\n(是/否/无法判断/观察受限/远程填写N/A）"] == "N/A"
    assert values["现场Roche员工"] == "N/A"
    assert values["有可疑参会人员\n(是/否/无法判断）"] == "无法判断"
    assert values["现场Roche员工人数"] == "N/A"
    assert statuses["现场确认单发送日期\n（PMO根据活动反馈邮件的日期填写）"] == "manual_required"
    assert values["备注\n（确认书写清楚）\n参考模板"] == "确认书写清楚"
    assert values["暗访会议备注"] == "N/A"
    assert statuses["累计计数"] == "manual_required"
    assert statuses["Level9"] == "manual_required"
    assert report["counts"]["missing"] == 0
