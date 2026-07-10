from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from app.services.domain.compliance.constants import DOCUMENT_CATEGORY_LABELS


def normalize_template_header(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[\s\r\n\t　（）()：:；;、/\\]+", "", text)


def flatten_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return "；".join(f"{k}:{flatten_value(v)}" for k, v in value.items() if v not in (None, "", [], {}))
    if isinstance(value, (list, tuple, set)):
        return "；".join(flatten_value(v) for v in value if v not in (None, "", [], {}))
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


@dataclass
class TemplateFieldResult:
    column: int
    header: str
    value: Any
    status: str
    source: str
    confidence: float
    evidence: str


class FactBag:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.sources: dict[str, str] = {}
        self.confidence: dict[str, float] = {}
        self.evidence: dict[str, str] = {}

    def set(
        self,
        key: str,
        value: Any,
        *,
        source: str,
        confidence: float = 0.8,
        evidence: str = "",
        overwrite: bool = False,
    ) -> None:
        if value in (None, "", [], {}):
            return
        if key in self.values and not overwrite:
            return
        self.values[key] = value
        self.sources[key] = source
        self.confidence[key] = max(0.0, min(float(confidence), 1.0))
        self.evidence[key] = evidence or source

    def set_if_better(
        self,
        key: str,
        value: Any,
        *,
        source: str,
        confidence: float = 0.8,
        evidence: str = "",
        prefer: bool = False,
    ) -> None:
        if value in (None, "", [], {}):
            return
        confidence = max(0.0, min(float(confidence), 1.0))
        if key not in self.values:
            self.set(key, value, source=source, confidence=confidence, evidence=evidence)
            return
        current_confidence = self.confidence.get(key, 0.0)
        current_value = self.values.get(key)
        if prefer or confidence > current_confidence or (
            confidence == current_confidence and len(str(value)) > len(str(current_value or ""))
        ):
            self.set(key, value, source=source, confidence=confidence, evidence=evidence, overwrite=True)

    def get(self, key: str) -> Any:
        return self.values.get(key)

    def result(self, column: int, header: str, key: str, value: Any | None = None) -> TemplateFieldResult:
        if value is None:
            value = self.get(key)
        return TemplateFieldResult(
            column=column,
            header=header,
            value=value,
            status="extracted" if self.sources.get(key, "").startswith("资料") else "derived",
            source=self.sources.get(key, "规则推断"),
            confidence=self.confidence.get(key, 0.75),
            evidence=self.evidence.get(key, ""),
        )


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


CONSENSUS_FIELD_FALLBACKS = {
    "actual_date",
    "actual_start_time",
    "actual_end_time",
    "actual_platform",
    "start_attendee_count",
    "end_attendee_count",
    "max_attendee_count",
    "speaker_name",
    "speaker_service_minutes",
    "actual_duration_minutes",
    "observation_success",
    "presentation_topic",
    "material_code",
    "ppt_pages",
}


def merge_vision_consensus_fallbacks(
    content_json: dict[str, Any],
    fields: dict[str, Any],
    field_confidence: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Use consensus fields as fallbacks when the primary vision pass drops structured values."""
    merged = dict(fields or {})
    confidences = dict(field_confidence or {})
    consensus = content_json.get("vision_consensus") if isinstance(content_json.get("vision_consensus"), dict) else {}
    consensus_fields = consensus.get("fields") if isinstance(consensus.get("fields"), dict) else {}
    consensus_conf = consensus.get("field_confidence") if isinstance(consensus.get("field_confidence"), dict) else {}
    for key in CONSENSUS_FIELD_FALLBACKS:
        value = consensus_fields.get(key)
        if not _is_present(value) or _is_present(merged.get(key)):
            continue
        merged[key] = value
        confidence = consensus_conf.get(key)
        if confidence not in (None, ""):
            try:
                confidences[key] = max(float(confidences.get(key) or 0), float(confidence))
            except (TypeError, ValueError):
                confidences[key] = confidence
    return merged, confidences


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def _money_value(value: Any) -> str:
    text = str(value or "").strip().replace(",", "")
    match = re.search(r"([\d]+(?:\.\d+)?)", text)
    if not match:
        return ""
    number = float(match.group(1))
    return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")


def _positive_int(value: Any) -> int | None:
    number = _safe_int(value)
    if number is None or number <= 0:
        return None
    return number


def _safe_time(value: Any) -> str | None:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    text = str(value or "").strip()
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if match:
        return f"{int(match.group(1)):02d}:{match.group(2)}"
    return None


def _safe_date(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    match = re.search(r"(20\d{6})", text)
    if match:
        raw = match.group(1)
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return None


def _valid_material_code(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"(?:A1P|SMS)\d+", text, re.I):
        return ""
    for pattern in (
        r"(?<![A-Z0-9])(?:P|NP)-[A-Z0-9][A-Z0-9.\-]*-\d{4}\.\d{2}-\d+(?![A-Z0-9])",
        r"(?<![A-Z0-9])M-CN-\d+(?![A-Z0-9])",
        r"(?<![A-Z0-9])Promotional-[^\s，,。；;]+",
    ):
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(0)
    return ""


def _material_code_display(value: Any) -> str:
    text = str(value or "").strip()
    code = _valid_material_code(text)
    if not code:
        return ""
    valid_until = re.search(r"valid\s*until\s*20\d{2}[./-]\d{1,2}", text, re.I)
    return f"{code} {valid_until.group(0)}" if valid_until else code


def _normal_count_text(value: Any) -> Any:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("＋", "+")
    combo = re.search(r"(\d{1,3})\D{0,10}\+\D{0,6}(\d{1,4})\s*人次", text)
    if combo:
        return f"{int(combo.group(1))}+{int(combo.group(2))}人次"
    leading = re.match(r"\s*(\d{1,3})\s*(?:人|名|位|个|陌医者|献者|医者)", text)
    if leading:
        return int(leading.group(1))
    number = _positive_int(text)
    return number if number is not None else text


def _count_rank(value: Any) -> int | None:
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value or "").strip()
    if not text or "+" in text:
        return None
    return _positive_int(text)


def _leading_count(value: Any) -> int | None:
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value or "").strip().replace("＋", "+")
    match = re.match(r"\s*(\d{1,3})\s*\+", text)
    if match:
        return int(match.group(1))
    return _positive_int(text)


def _count_sign_in_from_text(text: str) -> int:
    if not text:
        return 0
    normalized = re.sub(r"\s+", "", text)
    explicit = re.findall(r"(?<!未)已签[到署]", normalized)
    if explicit:
        return len(explicit)
    success = re.findall(r"签到(?:成功|完成|记录)", normalized)
    if success and len(success) > 1:
        return len(success)
    return 0


def _valid_text_value(value: Any) -> str:
    return str(value or "").strip().strip("：:，,。；;")


def _is_unknown_text(value: Any) -> bool:
    return _valid_text_value(value) in {"未知", "不详", "未识别", "无法判断", "待补充/需核实"}


def _valid_person_name(value: Any) -> str:
    text = _valid_text_value(value).replace("教授", "").strip()
    if not text:
        return ""
    if text in {"讲者", "主席", "讲者身份", "临床医生", "国家级", "省级", "市级", "未知"}:
        return ""
    match = re.search(r"([\u4e00-\u9fff]{2,4})", text)
    return match.group(1) if match else text


def _extract_label_value(text: str, label: str, *, max_len: int = 80) -> str:
    match = re.search(rf"{re.escape(label)}\s*[：:]\s*([^\n\r]+)", text)
    if not match:
        return ""
    return _valid_text_value(match.group(1)[:max_len])


def _extract_time_range_from_confirmation(text: str) -> tuple[str | None, str | None, str | None]:
    date_value = _safe_date(text)
    patterns = (
        r"实际(?:会议)?开始(?:时间)?\s*[:：]?\s*(\d{1,2}:\d{2}).{0,24}?(?:实际(?:会议)?(?:结束|结束时间)|结束)\s*[:：]?\s*(\d{1,2}:\d{2})",
        r"实际开始\s*(\d{1,2}:\d{2})\s*[，,、；;]\s*结束\s*(\d{1,2}:\d{2})",
        r"(\d{1,2}:\d{2})\s*[-~至]\s*(\d{1,2}:\d{2}).{0,12}?(?:线上会议|会议|时长)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return date_value, _safe_time(match.group(1)), _safe_time(match.group(2))
    return date_value, None, None


def _extract_confirmation_attendee_counts(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    specs = {
        "start_attendee_count": ("实际会议开始人数", "开始时人数", "开始人数"),
        "max_attendee_count": ("实际会议最大人数", "会中最大人数", "最大人数"),
        "end_attendee_count": ("实际会议结束人数", "结束时人数", "结束人数"),
    }
    for key, labels in specs.items():
        for label in labels:
            pattern = rf"{label}[^\d+＋]{{0,24}}(\d{{1,3}})[^\d+＋]{{0,18}}[+＋][^\d]{{0,8}}(\d{{1,4}})\s*人次"
            match = re.search(pattern, text)
            if match:
                out[key] = f"{int(match.group(1))}+{int(match.group(2))}人次"
                break
    return out


def _extract_agenda_schedule(text: str) -> tuple[str | None, str | None, str | None, int | None]:
    date_value = None
    start_time = None
    end_time = None
    duration = None
    date_match = re.search(
        r"(?:^|[\n\r])(?:日期|会议日期)[^\S\r\n]*[：:]?[^\S\r\n]*(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2})",
        text,
    )
    if date_match:
        date_value = _safe_date(date_match.group(1))
    time_match = re.search(
        r"(?:^|[\n\r])(?:时间|会议时间)[^\S\r\n]*[：:]?[^\S\r\n]*(\d{1,2}:\d{2})[^\S\r\n]*[-~至][^\S\r\n]*(\d{1,2}:\d{2})(?:[（(][^\S\r\n]*(\d{1,3})[^\S\r\n]*分钟[^\S\r\n]*[）)])?",
        text,
    )
    if not time_match:
        compact = re.sub(r"\s+", " ", text)
        time_match = re.search(
            r"(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})\s+(\d{1,2}:\d{2})\s*[-~至]\s*(\d{1,2}:\d{2})",
            compact,
        )
        if time_match and not date_value:
            date_value = _safe_date(time_match.group(1))
            start_time = _safe_time(time_match.group(2))
            end_time = _safe_time(time_match.group(3))
    else:
        start_time = _safe_time(time_match.group(1))
        end_time = _safe_time(time_match.group(2))
        duration = _positive_int(time_match.group(3))
    if duration is None:
        duration = _duration_minutes(start_time, end_time)
    if duration is not None and duration > 240:
        start_time = None
        end_time = None
        duration = None
    return date_value, start_time, end_time, duration


def _extract_presentation_topic_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for pattern in (
        r"(?:会议标题|PPT主题|演讲主题|主题|标题)[为：:「“'\"]+([^」”\"'\n。；;]{8,90})",
        r"(新剂型[-—－]?[助动]力HER2阳性晚期一线[^。\n；;]{4,50}治愈)",
    ):
        for match in re.finditer(pattern, text, re.I):
            value = re.sub(r"\s+", "", match.group(1)).strip(" ，,。；;：:")
            if value and ("HER2" in value.upper() or "新剂型" in value):
                candidates.append(value)
    return list(dict.fromkeys(candidates))


def _presentation_topic_score(topic: str, base_confidence: float) -> float:
    score = base_confidence
    if "助力" in topic:
        score += 0.08
    if "-" in topic or "－" in topic or "—" in topic:
        score += 0.04
    if "走向" in topic:
        score += 0.03
    if "动力" in topic:
        score -= 0.08
    return max(0.0, min(score, 0.98))


def _duration_minutes(start_hhmm: str | None, end_hhmm: str | None) -> int | None:
    if not start_hhmm or not end_hhmm:
        return None
    try:
        sh, sm = [int(x) for x in start_hhmm.split(":")[:2]]
        eh, em = [int(x) for x in end_hhmm.split(":")[:2]]
    except ValueError:
        return None
    duration = eh * 60 + em - (sh * 60 + sm)
    if duration < 0:
        duration += 24 * 60
    return duration


def _observer_name(meeting_case: dict[str, Any]) -> str | None:
    explicit = meeting_case.get("observer") or meeting_case.get("观察员名字")
    if explicit:
        return str(explicit).strip()
    source = str(meeting_case.get("source_folder") or "")
    folder_name = Path(source).name
    match = re.match(r"Remote_[^_]+_\d{8}_(.+)_Supporting$", folder_name)
    if match:
        return match.group(1).strip()
    return None


def _iter_material_fields(materials: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for material in materials:
        fields = material.get("fields") if isinstance(material.get("fields"), dict) else {}
        if fields:
            out.append((material, fields))
    return out


def _iter_sheet_rows(materials: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    rows: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for material in materials:
        sheets = material.get("sheets") or []
        if not isinstance(sheets, list):
            continue
        for sheet in sheets:
            for row in sheet.get("rows") or []:
                if isinstance(row, dict) and isinstance(row.get("values"), dict):
                    rows.append((material, sheet, row))
    return rows


def _all_material_text(materials: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for material in materials:
        parts.append(str(material.get("file_name") or ""))
        parts.append(str(material.get("document_category") or ""))
        parts.append(str(material.get("text_content") or ""))
        parts.append(str(material.get("md_results") or ""))
        fields = material.get("fields")
        if isinstance(fields, dict):
            parts.append(flatten_value(fields))
        for sheet in material.get("sheets") or []:
            for pre in sheet.get("pre_header_rows") or []:
                parts.append(flatten_value(pre))
    return "\n".join(p for p in parts if p)


def _meeting_time_range(text: str) -> tuple[str | None, str | None, str | None]:
    match = re.search(
        r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\s+(\d{1,2}):(\d{2})\s*[-~至]\s*(\d{1,2}):(\d{2})",
        text,
    )
    if not match:
        return None, None, None
    y, mo, d, sh, sm, eh, em = match.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}", f"{int(sh):02d}:{sm}", f"{int(eh):02d}:{em}"


def _populate_case_facts(facts: FactBag, meeting_case: dict[str, Any]) -> None:
    case_aliases = {
        "observation_type": ("observation_type", "观察类型"),
        "observation_success": ("observation_success", "本场会议是否成功观察"),
        "organizer_cooperation": ("organizer_cooperation", "会议组织者配合程度"),
        "surprise_check": ("surprise_check", "是否是Surprise Check\n联系组织者为“否”\n不联系组织者为“是”"),
        "meeting_type": ("meeting_type", "会议类型"),
        "meeting_code": ("meeting_code", "会议编码"),
        "total_budget": ("total_budget", "总预算金额"),
        "payment_method": ("payment_method", "付款方式（Simplebuy/Concur/A1）"),
        "pr_number": ("pr_number", "PR号码\n(Simplebuy)"),
        "bu": ("bu", "BU"),
        "applicant": ("applicant", "申请人姓名"),
        "planned_organizer_name": ("planned_organizer_name", "计划组织者姓名"),
        "actual_organizer_name": ("actual_organizer_name", "实际组织者姓名", "planned_organizer_name", "applicant"),
        "organizer_department": ("organizer_department",),
        "line_manager_name": ("line_manager_name", "直线经理姓名"),
        "line_manager_email": ("line_manager_email", "直线经理邮箱"),
        "product_name": ("product_name", "产品名称"),
        "province": ("province", "省份"),
        "city": ("city", "城市"),
        "meeting_location_type": ("meeting_location_type", "会议地点类型"),
        "planned_date": ("meeting_date", "会议计划日期", "实际会议日期"),
        "planned_start_time": ("计划开始时间",),
        "planned_roche_staff": ("planned_roche_staff", "计划参会罗氏员工"),
        "actual_date": ("实际会议日期", "meeting_date"),
        "actual_start_time": ("实际会议开始时间",),
        "actual_end_time": ("实际会议结束时间",),
        "planned_attendees": ("planned_attendees", "计划参会人数（不包含罗氏员工）"),
        "actual_sign_in_count": ("actual_sign_in_count", "签到人数（不含Roche员工）"),
        "speaker_name": ("speaker_name", "所有讲者姓名\n（请在括号中填写是否付费或罗氏员工）"),
        "speaker_service_minutes": ("speaker_service_minutes", "speaker_duration"),
        "planned_speaker_budget": ("planned_speaker_budget",),
        "material_code": ("material_code", "PPT主题及编码"),
        "presentation_topic": ("presentation_topic",),
        "ppt_pages": ("ppt_pages",),
    }
    normalized_case = {normalize_template_header(k): v for k, v in meeting_case.items()}
    for key, aliases in case_aliases.items():
        for alias in aliases:
            value = meeting_case.get(alias)
            if value in (None, ""):
                value = normalized_case.get(normalize_template_header(alias))
            if _is_present(value):
                if key == "actual_sign_in_count":
                    value = _positive_int(value)
                    if value is None:
                        continue
                if key == "material_code":
                    value = _valid_material_code(value)
                    if not value:
                        continue
                if key == "speaker_name":
                    value = _valid_person_name(value)
                    if not value:
                        continue
                facts.set(key, value, source="案件元数据", confidence=0.86, evidence=f"{alias}={value}")
                break

    folder_text = " ".join([str(meeting_case.get("source_folder") or ""), str(meeting_case.get("meeting_code") or "")])
    if not facts.get("observation_type") and re.search(r"(^|[_\-\s])remote([_\-\s]|$)", folder_text, re.I):
        facts.set("observation_type", "远程观察", source="文件夹命名", confidence=0.78, evidence=folder_text)
    if facts.get("observation_type") and "远程" in str(facts.get("observation_type")):
        facts.set("leave_time", "N/A", source="远程观察规则", confidence=0.9, evidence="远程观察填 N/A")
    observer = _observer_name(meeting_case)
    if observer:
        facts.set("observer_name", observer, source="文件夹命名", confidence=0.84, evidence=str(meeting_case.get("source_folder") or ""))

    code = str(facts.get("meeting_code") or "")
    if code.startswith("SMS") and not facts.get("meeting_type"):
        facts.set("meeting_type", "赞助会", source="会议编码规则", confidence=0.72, evidence=code)
    if code.startswith("SMS") and not facts.get("payment_method"):
        facts.set("payment_method", "N/A", source="会议编码规则", confidence=0.68, evidence="SMS 会议非 A1/Simplebuy 付款字段")
    if code.startswith("SMS") and not facts.get("pr_number"):
        facts.set("pr_number", "N/A", source="会议编码规则", confidence=0.68, evidence="SMS 会议无 Simplebuy PR")
    if code.startswith("A1P") and not facts.get("payment_method"):
        facts.set("payment_method", "A1", source="会议编码规则", confidence=0.75, evidence=code)
    if code.startswith("A1P") and not facts.get("pr_number"):
        facts.set("pr_number", "N/A", source="会议编码规则", confidence=0.68, evidence="A1 会议无 Simplebuy PR")
    if not facts.get("bu") and facts.get("organizer_department"):
        facts.set("bu", facts.get("organizer_department"), source="A1 组织者部门", confidence=0.72, evidence=str(facts.get("organizer_department")))
    if meeting_case.get("has_confirmation") and not facts.get("observation_success"):
        facts.set("observation_success", "是", source="资料分类", confidence=0.68, evidence="已导入现场确认单/确认单")
    if not facts.get("surprise_check"):
        facts.set("surprise_check", "否", source="默认观察流程规则", confidence=0.55, evidence="未识别 Surprise Check 证据")


def _populate_material_field_facts(facts: FactBag, materials: list[dict[str, Any]]) -> None:
    field_map = {
        "meeting_code": "meeting_code",
        "observation_success": "observation_success",
        "speaker_name": "speaker_name",
        "speaker_service_minutes": "speaker_service_minutes",
        "actual_duration_minutes": "actual_duration_minutes",
        "planned_duration_minutes": "planned_duration_minutes",
        "planned_start_time": "planned_start_time",
        "planned_end_time": "planned_end_time",
        "planned_attendees": "planned_attendees",
        "actual_sign_in_count": "actual_sign_in_count",
        "actual_date": "actual_date",
        "actual_start_time": "actual_start_time",
        "actual_end_time": "actual_end_time",
        "start_attendee_count": "start_attendee_count",
        "max_attendee_count": "max_attendee_count",
        "end_attendee_count": "end_attendee_count",
        "material_code": "material_code",
        "presentation_topic": "presentation_topic",
        "ppt_pages": "ppt_pages",
        "actual_platform": "actual_platform",
        "actual_sponsor": "actual_sponsor",
        "other_company_seen": "other_company_seen",
        "other_company_name": "other_company_name",
        "paid_speaker_count": "paid_speaker_count",
        "paid_chair_count": "paid_chair_count",
    }
    sign_in_total = 0
    sign_in_sources: list[str] = []
    sign_in_counted_files: set[str] = set()
    max_attendee_candidates: list[dict[str, Any]] = []
    start_end_candidates: dict[str, list[dict[str, Any]]] = {
        "start_attendee_count": [],
        "end_attendee_count": [],
    }
    for material, fields in _iter_material_fields(materials):
        category = str(material.get("document_category") or "")
        source = f"资料字段:{material.get('file_name') or ''}"
        confs = material.get("field_confidence") if isinstance(material.get("field_confidence"), dict) else {}
        for src_key, fact_key in field_map.items():
            value = fields.get(src_key)
            if _is_present(value):
                if fact_key in {"presentation_topic", "material_code", "ppt_pages"} and category not in {
                    "presentation_material",
                    "observation_confirmation",
                }:
                    continue
                if fact_key == "actual_sign_in_count":
                    count = _positive_int(value)
                    if count:
                        sign_in_total += count
                        sign_in_sources.append(source)
                        sign_in_counted_files.add(str(material.get("file_name") or ""))
                    continue
                if fact_key == "material_code":
                    value = _valid_material_code(value)
                    if not value:
                        continue
                if fact_key == "speaker_name":
                    value = _valid_person_name(value)
                    if not value:
                        continue
                if fact_key == "actual_platform" and _is_unknown_text(value):
                    continue
                if fact_key in {"start_attendee_count", "max_attendee_count", "end_attendee_count"}:
                    value = _normal_count_text(value)
                    confidence = float(confs.get(src_key) or fields.get("vision_confidence") or 0.72)
                    candidate = {
                        "value": value,
                        "source": source,
                        "confidence": confidence,
                        "evidence": fields.get("summary_text") or material.get("text_content") or source,
                        "document_category": category,
                    }
                    if fact_key in start_end_candidates:
                        start_end_candidates[fact_key].append(candidate)
                        continue
                    if fact_key == "max_attendee_count":
                        max_attendee_candidates.append(candidate)
                        continue
                if fact_key == "ppt_pages":
                    candidate = _positive_int(value)
                    if candidate is None:
                        continue
                    value = candidate
                confidence = float(confs.get(src_key) or fields.get("vision_confidence") or 0.72)
                if fact_key in {"start_attendee_count", "end_attendee_count"} and category == "meeting_screenshot":
                    confidence = min(confidence, 0.62)
                if fact_key in {
                    "actual_platform",
                    "speaker_name",
                    "planned_start_time",
                    "planned_end_time",
                    "presentation_topic",
                    "start_attendee_count",
                    "end_attendee_count",
                }:
                    facts.set_if_better(
                        fact_key,
                        value,
                        source=source,
                        confidence=confidence,
                        evidence=fields.get("summary_text") or material.get("text_content") or source,
                        prefer=category == "observation_confirmation",
                    )
                else:
                    facts.set(
                        fact_key,
                        value,
                        source=source,
                        confidence=confidence,
                        evidence=fields.get("summary_text") or material.get("text_content") or source,
                    )
    for material in materials:
        if material.get("document_category") != "sign_in_record":
            continue
        file_name = str(material.get("file_name") or "")
        if file_name in sign_in_counted_files:
            continue
        text_count = _count_sign_in_from_text(_material_text(material))
        if text_count:
            sign_in_total += text_count
            sign_in_sources.append(f"资料文本:{file_name}")

    if max_attendee_candidates:
        numeric_candidates = [
            {**item, "rank": _count_rank(item.get("value"))}
            for item in max_attendee_candidates
            if _count_rank(item.get("value")) is not None
        ]
        if numeric_candidates:
            chosen = max(numeric_candidates, key=lambda item: (int(item["rank"]), float(item["confidence"])))
            value = int(chosen["rank"])
        else:
            chosen = max(max_attendee_candidates, key=lambda item: float(item["confidence"]))
            value = chosen["value"]
        facts.set_if_better(
            "max_attendee_count",
            value,
            source=chosen["source"],
            confidence=chosen["confidence"],
            evidence=chosen["evidence"],
            prefer=True,
        )
        if chosen.get("document_category") == "meeting_screenshot" and _count_rank(value) is not None:
            facts.set_if_better(
                "zoom_peak_count",
                int(_count_rank(value) or 0),
                source=chosen["source"],
                confidence=chosen["confidence"],
                evidence=chosen["evidence"],
                prefer=True,
            )
        facts.set(
            "attendee_count_candidates",
            [
                {
                    "value": item["value"],
                    "source": item["source"],
                    "document_category": item["document_category"],
                    "confidence": round(float(item["confidence"]), 4),
                }
                for item in max_attendee_candidates
            ],
            source="人数证据候选",
            confidence=0.7,
            evidence="端口/确认单人数候选",
        )

    for fact_key, candidates in start_end_candidates.items():
        if not candidates:
            continue
        priority = {
            "observation_confirmation": 4,
            "a1_meeting_export": 3,
            "meeting_agenda": 2,
            "meeting_screenshot": 1,
        }
        chosen = max(
            candidates,
            key=lambda item: (
                priority.get(str(item.get("document_category") or ""), 0),
                float(item.get("confidence") or 0),
            ),
        )
        facts.set_if_better(
            fact_key,
            chosen["value"],
            source=chosen["source"],
            confidence=chosen["confidence"],
            evidence=chosen["evidence"],
            prefer=True,
        )

    current_sign_in = _positive_int(facts.get("actual_sign_in_count"))
    if sign_in_total and not current_sign_in:
        facts.set(
            "actual_sign_in_count",
            sign_in_total,
            source="资料字段:签到记录汇总",
            confidence=0.86,
            evidence="；".join(sign_in_sources[:6]),
        )


def _populate_attendance_expression(facts: FactBag) -> None:
    watch_count = _positive_int(facts.get("watch_record_count"))
    start_count = _leading_count(facts.get("start_attendee_count"))
    if watch_count and start_count:
        facts.set_if_better(
            "total_attendance_expression",
            f"{start_count}+{watch_count}人次",
            source="人数口径拆分",
            confidence=min(facts.confidence.get("watch_record_count", 0.82), facts.confidence.get("start_attendee_count", 0.72)),
            evidence="开始端口人数 + 直播观看记录有效行数",
            prefer=True,
        )


def _material_text(material: dict[str, Any]) -> str:
    parts = [
        str(material.get("file_name") or ""),
        str(material.get("document_category") or ""),
        str(material.get("text_content") or ""),
        str(material.get("md_results") or ""),
    ]
    fields = material.get("fields")
    if isinstance(fields, dict):
        parts.append(flatten_value(fields))
    return "\n".join(p for p in parts if p)


def _populate_confirmation_text_facts(facts: FactBag, materials: list[dict[str, Any]]) -> None:
    for material in materials:
        if material.get("document_category") != "observation_confirmation":
            continue
        text = _material_text(material)
        source = f"确认单:{material.get('file_name') or ''}"
        meeting_date, start_time, end_time = _extract_time_range_from_confirmation(text)
        if meeting_date:
            facts.set_if_better("actual_date", meeting_date, source=source, confidence=0.88, evidence=text[:220], prefer=True)
        if start_time:
            facts.set_if_better("actual_start_time", start_time, source=source, confidence=0.88, evidence=text[:220], prefer=True)
        if end_time:
            facts.set_if_better("actual_end_time", end_time, source=source, confidence=0.88, evidence=text[:220], prefer=True)
        if re.search(r"\bzoom\b|ZOOM|腾讯会议|Teams|Webex|线上", text, re.I):
            if re.search(r"\bzoom\b|ZOOM", text, re.I):
                platform = "ZOOM"
            elif "腾讯会议" in text:
                platform = "腾讯会议"
            else:
                platform = "线上平台"
            facts.set_if_better("actual_platform", platform, source=source, confidence=0.84, evidence=text[:180], prefer=True)
        for key, value in _extract_confirmation_attendee_counts(text).items():
            facts.set_if_better(key, value, source=source, confidence=0.84, evidence=text[:240], prefer=True)


def _populate_presentation_text_facts(facts: FactBag, materials: list[dict[str, Any]]) -> None:
    for material in materials:
        text = _material_text(material)
        if not text:
            continue
        fields = material.get("fields") if isinstance(material.get("fields"), dict) else {}
        confs = material.get("field_confidence") if isinstance(material.get("field_confidence"), dict) else {}
        base_confidence = float(
            confs.get("presentation_topic")
            or fields.get("vision_confidence")
            or material.get("confidence")
            or 0.64
        )
        source = f"资料文本:{material.get('file_name') or ''}"
        for topic in _extract_presentation_topic_candidates(text):
            facts.set_if_better(
                "presentation_topic",
                topic,
                source=source,
                confidence=_presentation_topic_score(topic, base_confidence),
                evidence=topic,
            )

        page_match = re.search(r"(?:幻灯片|slide)[^\d]{0,10}\d{1,3}\s*/\s*(\d{1,3})", text, re.I)
        if not page_match:
            page_match = re.search(r"(?:共|总页数|页数|共计)[^\d]{0,8}(\d{1,3})\s*页", text, re.I)
        if page_match:
            pages = _positive_int(page_match.group(1))
            if pages and pages > 1:
                facts.set_if_better(
                    "ppt_pages",
                    pages,
                    source=source,
                    confidence=max(0.76, min(base_confidence + 0.14, 0.94)),
                    evidence=page_match.group(0),
                    prefer=True,
                )

        display_code = _material_code_display(text)
        if display_code:
            facts.set_if_better(
                "material_code_display",
                display_code,
                source=source,
                confidence=max(0.76, min(base_confidence + 0.08, 0.95)),
                evidence=display_code,
            )


def _populate_watch_excel_facts(facts: FactBag, materials: list[dict[str, Any]]) -> None:
    for material, sheet, row in _iter_sheet_rows(materials):
        values = row.get("values") or {}
        if not {"会议时间", "观众姓名"}.issubset(values.keys()):
            continue
        meeting_time = str(values.get("会议时间") or "")
        meeting_date, start_time, end_time = _meeting_time_range(meeting_time)
        source = f"资料表格:{material.get('file_name') or ''}/{sheet.get('sheet_name') or ''}"
        if meeting_date:
            facts.set("planned_date", meeting_date, source=source, confidence=0.82, evidence=meeting_time)
            facts.set("actual_date", meeting_date, source=source, confidence=0.82, evidence=meeting_time)
        if start_time:
            facts.set("planned_start_time", start_time, source=source, confidence=0.78, evidence=meeting_time)
            facts.set("actual_start_time", start_time, source=source, confidence=0.78, evidence=meeting_time)
        if end_time:
            facts.set("actual_end_time", end_time, source=source, confidence=0.72, evidence=meeting_time)
        chair = values.get("会议主席")
        if _is_present(chair):
            facts.set("meeting_chair", str(chair).strip(), source=source, confidence=0.78, evidence=f"会议主席={chair}")
        break

    for material, sheet, _row in _iter_sheet_rows(materials):
        rows = sheet.get("rows") or []
        if not rows:
            continue
        headers = set((rows[0].get("values") or {}).keys())
        if {"会议时间", "观众姓名", "登录时间", "登录时长"}.issubset(headers):
            count = sum(1 for r in rows if (r.get("values") or {}).get("观众姓名"))
            source = f"资料表格:{material.get('file_name') or ''}/{sheet.get('sheet_name') or ''}"
            facts.set("attendance_source", "watch_record", source=source, confidence=0.9, evidence="线上直播观看数据")
            facts.set("watch_record_count", count, source=source, confidence=0.82, evidence=f"观看记录有效行数={count}")
            pre_text = flatten_value(sheet.get("pre_header_rows") or "")
            if pre_text:
                title = re.sub(r"\s*线上直播观看数据\s*$", "", pre_text).strip()
                if title:
                    facts.set("meeting_title", title, source=source, confidence=0.72, evidence=pre_text[:180])


def _populate_text_facts(facts: FactBag, materials: list[dict[str, Any]]) -> None:
    text = _all_material_text(materials)
    compact = re.sub(r"\s+", " ", text)
    if not facts.get("meeting_type"):
        value = _extract_label_value(text, "会议类型")
        if value:
            facts.set("meeting_type", value, source="资料文本", confidence=0.76, evidence=f"会议类型:{value}")
    if not facts.get("applicant"):
        value = _extract_label_value(text, "会议申请人")
        value = re.split(r"[（(]", value)[0].strip() if value else ""
        if value:
            facts.set("applicant", value, source="资料文本", confidence=0.76, evidence=f"会议申请人:{value}")
    if not facts.get("planned_organizer_name"):
        value = _extract_label_value(text, "会议组织者")
        value = re.split(r"[（(]", value)[0].strip() if value else ""
        if value:
            facts.set("planned_organizer_name", value, source="资料文本", confidence=0.76, evidence=f"会议组织者:{value}")
            facts.set("actual_organizer_name", value, source="资料文本", confidence=0.72, evidence=f"会议组织者:{value}")
    if not facts.get("organizer_department"):
        value = _extract_label_value(text, "组织者部门")
        if value:
            facts.set("organizer_department", value, source="资料文本", confidence=0.72, evidence=f"组织者部门:{value}")
    if not facts.get("bu") and facts.get("organizer_department"):
        facts.set("bu", facts.get("organizer_department"), source="资料文本", confidence=0.68, evidence=str(facts.get("organizer_department")))
    if not facts.get("line_manager_name"):
        value = _extract_label_value(text, "直 线 经 理") or _extract_label_value(text, "直线经理")
        name = re.split(r"[（(]", value)[0].strip() if value else ""
        if name:
            facts.set("line_manager_name", name, source="资料文本", confidence=0.72, evidence=f"直线经理:{value}")
        email_match = re.search(r"直\s*线\s*经\s*理[：:][^\n\r]*?([A-Za-z0-9._%+-]+@roche\.com)", text, re.I)
        if email_match:
            facts.set("line_manager_email", email_match.group(1), source="资料文本", confidence=0.72, evidence=email_match.group(0))
    if not facts.get("product_name"):
        value = _extract_label_value(text, "产品")
        if value:
            facts.set("product_name", value, source="资料文本", confidence=0.74, evidence=f"产品:{value}")
    if not facts.get("city"):
        value = _extract_label_value(text, "会议城市")
        if value:
            facts.set("city", value, source="资料文本", confidence=0.74, evidence=f"会议城市:{value}")
            if value in {"北京市", "上海市", "天津市", "重庆市"}:
                facts.set("province", value, source="资料文本", confidence=0.7, evidence=f"直辖市:{value}")
    if not facts.get("meeting_location_type"):
        value = _extract_label_value(text, "院内/院外")
        if value:
            facts.set("meeting_location_type", value, source="资料文本", confidence=0.72, evidence=f"院内/院外:{value}")
    if not facts.get("planned_attendees") or not facts.get("planned_roche_staff"):
        attendees = re.search(
            r"会议人数[：:]?\s*总人数[：:]?\s*(\d+).*?内部人数[：:]?\s*(\d+).*?外部人数[：:]?\s*(\d+)",
            text,
            re.S,
        )
        if attendees:
            facts.set("planned_roche_staff", int(attendees.group(2)), source="资料文本", confidence=0.8, evidence=attendees.group(0)[:160])
            facts.set("planned_attendees", int(attendees.group(3)), source="资料文本", confidence=0.8, evidence=attendees.group(0)[:160])
    if not facts.get("planned_speaker_budget"):
        budget_match = re.search(r"讲课费预算小计[：:]\s*[￥¥]?\s*([\d,]+(?:\.\d+)?)", text)
        if budget_match:
            facts.set("planned_speaker_budget", budget_match.group(1).replace(",", ""), source="资料文本", confidence=0.76, evidence=budget_match.group(0))
    if not facts.get("total_budget"):
        for pattern in (
            r"会议总预算（含讲课费）[：:]\s*[￥¥]?\s*([\d,]+(?:\.\d+)?)",
            r"计划会议预算（含讲课费）[：:]\s*[￥¥]?\s*([\d,]+(?:\.\d+)?)",
        ):
            budget_match = re.search(pattern, text)
            if budget_match:
                facts.set("total_budget", _money_value(budget_match.group(1)), source="资料文本", confidence=0.78, evidence=budget_match.group(0))
                break
    if not facts.get("planned_other_budget"):
        video_budget = re.search(r"视频会议\s*(?:\n|\r|\s)+([\d,]+(?:\.\d+)?)", text)
        if video_budget:
            amount = _money_value(video_budget.group(1))
            if amount:
                facts.set("planned_other_budget", f"{amount}（视频会议）", source="资料文本", confidence=0.76, evidence=video_budget.group(0))
    if not facts.get("paid_speaker_count"):
        speaker_count = re.search(r"讲者级别[：:]\s*[^\n\r]*?(\d+)\s*人", text)
        if speaker_count:
            facts.set("paid_speaker_count", int(speaker_count.group(1)), source="资料文本", confidence=0.72, evidence=speaker_count.group(0))
    if facts.get("paid_speaker_count") and not facts.get("paid_chair_count"):
        facts.set("paid_chair_count", 0, source="资料文本", confidence=0.55, evidence="未识别付费主席")
    if not facts.get("speaker_name"):
        speaker = re.search(r"\n([\u4e00-\u9fff]{2,4})\n临床医生\n(?:国家级|省级|市级)", text)
        if speaker:
            facts.set("speaker_name", speaker.group(1), source="资料文本", confidence=0.78, evidence=speaker.group(0))
    for material in materials:
        if material.get("document_category") not in {"meeting_agenda", "a1_meeting_export"}:
            continue
        material_text = _material_text(material)
        agenda_date, agenda_start, agenda_end, agenda_duration = _extract_agenda_schedule(material_text)
        if not any([agenda_date, agenda_start, agenda_end, agenda_duration]):
            continue
        source = f"资料文本:{material.get('file_name') or ''}"
        prefer_schedule = material.get("document_category") == "meeting_agenda"
        confidence = 0.84 if prefer_schedule else 0.76
        if agenda_date:
            facts.set_if_better("planned_date", agenda_date, source=source, confidence=confidence, evidence=agenda_date, prefer=prefer_schedule)
        if agenda_start:
            facts.set_if_better("planned_start_time", agenda_start, source=source, confidence=confidence, evidence=f"{agenda_start}-{agenda_end or ''}", prefer=prefer_schedule)
            facts.set_if_better("speaker_start_time", agenda_start, source=source, confidence=confidence, evidence=f"{agenda_start}-{agenda_end or ''}", prefer=prefer_schedule)
        if agenda_end:
            facts.set_if_better("planned_end_time", agenda_end, source=source, confidence=confidence, evidence=f"{agenda_start or ''}-{agenda_end}", prefer=prefer_schedule)
            facts.set_if_better("speaker_end_time", agenda_end, source=source, confidence=confidence, evidence=f"{agenda_start or ''}-{agenda_end}", prefer=prefer_schedule)
        if agenda_duration:
            facts.set_if_better("planned_duration_minutes", agenda_duration, source=source, confidence=confidence, evidence=f"议程时长 {agenda_duration} 分钟", prefer=prefer_schedule)
            facts.set_if_better("speaker_service_minutes", agenda_duration, source=source, confidence=confidence, evidence=f"议程时长 {agenda_duration} 分钟", prefer=prefer_schedule)
    if not facts.get("meeting_title"):
        title = _extract_label_value(text, "主题", max_len=100) or _extract_label_value(text, "会议主题", max_len=100)
        if title:
            facts.set("meeting_title", title, source="资料文本:议程", confidence=0.72, evidence=f"主题:{title}")
    if not facts.get("meeting_code"):
        match = re.search(r"(?<![A-Z0-9])((?:A1P|SMS)\d+)(?![A-Z0-9])", text, re.I)
        if match:
            facts.set("meeting_code", match.group(1).upper(), source="资料文本", confidence=0.76, evidence=match.group(0))
    if not facts.get("actual_platform"):
        zoom = re.search(r"zoom\s*([0-9]{8,})", compact, re.I)
        if zoom:
            facts.set("actual_platform", f"ZOOM {zoom.group(1)}", source="资料文本", confidence=0.72, evidence=zoom.group(0))
        elif "腾讯会议" in compact:
            facts.set("actual_platform", "腾讯会议", source="资料文本", confidence=0.68, evidence="腾讯会议")
        elif "线上" in compact:
            facts.set("actual_platform", "线上平台", source="资料文本", confidence=0.62, evidence="线上")
    if not facts.get("material_code"):
        code = _valid_material_code(compact)
        if code:
            facts.set("material_code", code, source="资料文本", confidence=0.68, evidence=code)
    if not facts.get("ppt_pages"):
        page = re.search(r"(?:ppt|PPT|总页数|页数)[^\d]{0,8}(\d{1,3})\s*页", compact)
        if page:
            facts.set("ppt_pages", int(page.group(1)), source="资料文本", confidence=0.64, evidence=page.group(0))
    if not facts.get("actual_sponsor"):
        sponsor = re.search(r"(中国医学基金会|中华医学会|中国医师协会|[^\s，,。；;]{2,20}基金会)", compact)
        if sponsor:
            facts.set("actual_sponsor", sponsor.group(1), source="资料文本", confidence=0.62, evidence=sponsor.group(0))
    if not facts.get("other_company_seen") and re.search(r"其他厂家|其他厂商|诺华|辉瑞|阿斯利康|礼来", compact):
        facts.set("other_company_seen", "是", source="资料文本", confidence=0.66, evidence="识别到其他厂家/厂商相关描述")


def build_template_fact_bag(
    meeting_case: dict[str, Any],
    parsed_materials: list[dict[str, Any]] | None = None,
) -> FactBag:
    facts = FactBag()
    materials = list(parsed_materials or [])
    _populate_case_facts(facts, meeting_case)
    _populate_material_field_facts(facts, materials)
    _populate_confirmation_text_facts(facts, materials)
    _populate_presentation_text_facts(facts, materials)
    _populate_watch_excel_facts(facts, materials)
    _populate_attendance_expression(facts)
    _populate_text_facts(facts, materials)
    categories = {str(material.get("document_category") or "") for material in materials}
    if "speaker_profile" in categories:
        facts.set("speaker_profile_present", "均有", source="资料分类", confidence=0.78, evidence="已识别讲者网络资料/讲者资料")
    if "observation_confirmation" in categories:
        facts.set("confirmation_present", "是", source="资料分类", confidence=0.78, evidence="已识别现场确认单/确认单")
    if not facts.get("organizer_cooperation") and facts.get("observation_success") in {"是", True, "true", "True"}:
        facts.set("organizer_cooperation", "配合", source="观察结果推断", confidence=0.62, evidence="成功观察且资料已接入")
    if facts.get("actual_start_time") and facts.get("actual_end_time"):
        minutes = _duration_minutes(str(facts.get("actual_start_time")), str(facts.get("actual_end_time")))
        if minutes is not None:
            facts.set("actual_duration_minutes", minutes, source="时间区间计算", confidence=0.72, evidence="实际开始/结束时间")
    if not facts.get("observation_success") and parsed_materials:
        facts.set("observation_success", "待补充/需核实", source="字段审计引擎", confidence=0.0, evidence="未识别现场确认结论")
    return facts


def _finding_texts(findings: list[dict]) -> list[str]:
    texts = []
    for item in findings:
        parts = [
            item.get("risk_category"),
            item.get("risk_subcategory"),
            item.get("problem"),
            item.get("rule_triggered"),
            item.get("suggestion"),
            flatten_value(item.get("evidence_json")),
        ]
        texts.append(normalize_template_header(" ".join(str(p or "") for p in parts)))
    return texts


RISK_FLAG_KEYWORDS: list[tuple[str, list[str]]] = [
    ("临时取消", ["临时取消", "取消"]),
    ("临时改期", ["临时改期", "改期", "延期"]),
    ("提前召开", ["提前召开", "提前"]),
    ("无法核实会议", ["无法核实会议", "无法验证会议", "限制入场", "无法联系组织者"]),
    ("无法核实用餐", ["无法核实用餐", "用餐无法核实"]),
    ("讲者身份认证与实际情况不符", ["讲者身份", "讲者不一致", "实际付费主席讲者与计划不一致"]),
    ("参会人身份认证与实际情况不符", ["参会人身份", "参会人员身份"]),
    ("会议现场出现其他厂商员工", ["其他厂商", "其他厂家", "竞品"]),
    ("最终使用的PPT", ["ppt", "编码", "未能体现编码"]),
    ("所使用的材料在会议前尚未完成系统最终审批流程", ["审批", "编码过期", "validuntil"]),
    ("付费讲者的讲课时间少于20分钟", ["少于20分钟", "讲课时间不足", "服务时间不足"]),
    ("会议整体时长不足", ["整体时长不足", "会议时长不足"]),
]


def risk_flag_for_header(header: str, finding_texts: list[str], facts: FactBag) -> int:
    normalized_header = normalize_template_header(header)
    for text in finding_texts:
        if normalized_header and (normalized_header in text or text in normalized_header):
            return 1
    for header_keyword, patterns in RISK_FLAG_KEYWORDS:
        if normalize_template_header(header_keyword) in normalized_header:
            if any(normalize_template_header(pattern) in text for pattern in patterns for text in finding_texts):
                return 1
    if "会议现场出现其他厂商员工" in header and facts.get("other_company_seen") == "是":
        return 1
    return 0


def summary_text(findings: list[dict]) -> str:
    if not findings:
        return "无"
    return "\n".join(
        f"{idx}. {item.get('problem') or item.get('risk_category') or '未命名 Finding'}"
        for idx, item in enumerate(findings, start=1)
    )


def follow_up_text(missing: list[dict], findings: list[dict]) -> str:
    lines: list[str] = []
    for item in missing:
        doc = item.get("document_type") or item.get("doc_type") or "资料"
        doc_label = DOCUMENT_CATEGORY_LABELS.get(str(doc), str(doc))
        reason = item.get("reason") or "缺少资料"
        lines.append(f"补充{doc_label}：{reason}")
    for item in findings:
        if item.get("manual_review_required"):
            lines.append(str(item.get("suggestion") or item.get("problem") or "需人工复核"))
    return "\n".join(f"{idx}. {text}" for idx, text in enumerate(lines, start=1)) if lines else "无"


def default_field_result(column: int, header: str) -> TemplateFieldResult:
    normalized = normalize_template_header(header)
    if (
        "pmo填写" in normalized
        or "内部订单号" in normalized
        or "组织者的级别" in normalized
        or "登陆账号" in normalized
        or "登录账号" in normalized
        or "现场确认单发送日期" in normalized
        or normalized in {"累计计数", "level9"}
    ):
        return TemplateFieldResult(column, header, "待PMO填写", "manual_required", "PMO字段", 0.0, "模板标明 PMO 填写")
    if normalized in {"rochecomments", "dttreply"}:
        return TemplateFieldResult(column, header, "待客户确认", "customer_required", "客户字段", 0.0, "模板标明客户/后续回复")
    if "如无" in header or "n/a" in normalized:
        return TemplateFieldResult(column, header, "N/A", "not_applicable", "模板规则", 0.7, "字段说明允许无则 N/A")
    if any(label in header for label in ("计划预算金额（餐费）", "计划预算金额（场租）", "计划预算金额（设备租赁）", "计划预算金额（包车）", "计划预算金额（住宿）")):
        return TemplateFieldResult(column, header, "N/A", "not_applicable", "A1预算规则", 0.72, "A1 导出未列示该预算项目")
    if "预算" in header:
        return TemplateFieldResult(column, header, "待PMO填写", "manual_required", "PMO字段", 0.0, "预算字段需由 A1/PMO 明细确认")
    if "金额" in header or "费用" in header or "用餐" in header or "茶歇" in header:
        return TemplateFieldResult(column, header, "N/A", "not_applicable", "默认规则", 0.45, "未识别到该费用/用餐证据")
    return TemplateFieldResult(column, header, "待补充/需核实", "missing", "字段审计引擎", 0.0, "当前资料未提供足够证据")


def build_fixed_template_field_results(
    headers: list[Any],
    meeting_case: dict[str, Any],
    findings: list[dict],
    missing: list[dict],
    parsed_materials: list[dict[str, Any]] | None = None,
) -> list[TemplateFieldResult]:
    facts = build_template_fact_bag(meeting_case, parsed_materials)
    finding_texts = _finding_texts(findings)
    results: list[TemplateFieldResult] = []
    risk_start = None
    risk_end = None
    for idx, raw_header in enumerate(headers, start=1):
        normalized = normalize_template_header(raw_header)
        if normalized == normalize_template_header("临时取消"):
            risk_start = idx
        if normalized.startswith(normalize_template_header("是否问题会议")):
            risk_end = idx
            break

    any_risk_flag = False
    for column, raw_header in enumerate(headers, start=1):
        header = str(raw_header or "").strip()
        if not header:
            results.append(TemplateFieldResult(column, header, None, "blank_header", "模板", 0.0, ""))
            continue
        normalized = normalize_template_header(header)

        if risk_start and risk_end and risk_start <= column < risk_end:
            value = risk_flag_for_header(header, finding_texts, facts)
            any_risk_flag = any_risk_flag or value == 1
            results.append(TemplateFieldResult(column, header, value, "rule", "Finding/事实规则", 0.74, header))
            continue
        if risk_end and column == risk_end:
            value = 1 if any_risk_flag or findings else 0
            results.append(TemplateFieldResult(column, header, value, "rule", "Finding汇总", 0.86, "前序风险列或 Finding"))
            continue
        if normalized == normalize_template_header("反馈类型（根据DO至DR列进行填写）"):
            value = "问题会议" if any_risk_flag or findings else "无问题会议"
            results.append(TemplateFieldResult(column, header, value, "rule", "Finding汇总", 0.86, "前序风险列或 Finding"))
            continue
        if normalized == normalize_template_header("观察点汇总（根据前面所选finding填写描述，需逐条写明问题点标题）"):
            results.append(TemplateFieldResult(column, header, summary_text(findings), "rule", "Finding清单", 0.86, "Finding problem"))
            continue
        if normalized == normalize_template_header("待跟进事项（无法在跟会现场或观察员收集的evidence不足以判断是否为finding，需进一步核实）"):
            results.append(TemplateFieldResult(column, header, follow_up_text(missing, findings), "rule", "缺件/Finding清单", 0.82, "missing + manual review"))
            continue
        if normalized.startswith(normalize_template_header("Potential Finding")):
            value = meeting_case.get("potential_finding") or meeting_case.get("Potential Finding") or "无"
            results.append(TemplateFieldResult(column, header, value, "rule", "案件/Finding规则", 0.7, "未识别正式 Potential Finding"))
            continue

        direct_map = {
            "观察类型": "observation_type",
            "本场会议是否成功观察": "observation_success",
            "会议组织者配合程度": "organizer_cooperation",
            "是否是Surprise Check\n联系组织者为“否”\n不联系组织者为“是”": "surprise_check",
            "会议类型": "meeting_type",
            "会议编码": "meeting_code",
            "总预算金额": "total_budget",
            "付款方式（Simplebuy/Concur/A1）": "payment_method",
            "PR号码\n(Simplebuy)": "pr_number",
            "BU": "bu",
            "申请人姓名": "applicant",
            "计划组织者姓名": "planned_organizer_name",
            "实际组织者姓名": "actual_organizer_name",
            "直线经理姓名": "line_manager_name",
            "直线经理邮箱": "line_manager_email",
            "产品名称": "product_name",
            "省份": "province",
            "城市": "city",
            "会议地点类型": "meeting_location_type",
            "会议计划日期": "planned_date",
            "计划开始时间": "planned_start_time",
            "计划预算金额（讲者）": "planned_speaker_budget",
            "计划参会罗氏员工": "planned_roche_staff",
            "实际会议日期": "actual_date",
            "实际会议开始时间": "actual_start_time",
            "实际会议结束时间": "actual_end_time",
            "讲者和主席演讲开始时间": "speaker_start_time",
            "讲者和主席演讲结束时间": "speaker_end_time",
            "讲者和主席讨论时长（分钟）": "speaker_discussion_minutes",
            "实际付费讲者人数": "paid_speaker_count",
            "实际付费主席人数": "paid_chair_count",
            "PPT页数": "ppt_pages",
            "实际主办方\n(如无的话写N/A）": "actual_sponsor",
            "观察员名字": "observer_name",
        }
        fact_key = None
        for label, key in direct_map.items():
            if normalized == normalize_template_header(label):
                fact_key = key
                break
        if fact_key and _is_present(facts.get(fact_key)):
            results.append(facts.result(column, header, fact_key))
            continue

        if normalized == normalize_template_header("计划会议地址（线上平台）"):
            value = facts.get("planned_platform") or ("线上平台" if "远程" in str(facts.get("observation_type") or "") else facts.get("actual_platform"))
            if _is_present(value):
                results.append(TemplateFieldResult(column, header, value, "derived", "观察类型推断", 0.58, "远程观察"))
                continue
        if normalized in {
            normalize_template_header("计划组织者登陆账号"),
            normalize_template_header("实际组织者登陆账号"),
        }:
            results.append(TemplateFieldResult(column, header, "待PMO填写", "manual_required", "PMO字段", 0.0, "登录账号不从观察资料推断"))
            continue
        if normalized in {
            normalize_template_header("计划预算金额（餐费）"),
            normalize_template_header("计划预算金额（场租）"),
            normalize_template_header("计划预算金额（设备租赁）"),
            normalize_template_header("计划预算金额（包车）"),
            normalize_template_header("计划预算金额（住宿）"),
        }:
            results.append(TemplateFieldResult(column, header, "N/A", "not_applicable", "A1预算规则", 0.72, "A1 导出未列示该预算项目"))
            continue
        if normalized == normalize_template_header("计划预算金额（其他____）"):
            value = facts.get("planned_other_budget") or "N/A"
            status = "derived" if value != "N/A" else "not_applicable"
            results.append(
                TemplateFieldResult(
                    column,
                    header,
                    value,
                    status,
                    facts.sources.get("planned_other_budget", "A1预算规则"),
                    facts.confidence.get("planned_other_budget", 0.72),
                    facts.evidence.get("planned_other_budget", "A1 导出未列示其他预算项目"),
                )
            )
            continue
        if normalized == normalize_template_header("实际会议地点（线上平台）"):
            value = facts.get("actual_platform") or ("线上平台" if "远程" in str(facts.get("observation_type") or "") else None)
            if _is_present(value):
                results.append(TemplateFieldResult(column, header, value, "derived", "资料文本/观察类型", 0.62, str(value)))
                continue
        if normalized == normalize_template_header("离场时间\n（远程观察填N/A）"):
            value = facts.get("actual_end_time") or facts.get("leave_time") or "N/A"
            results.append(TemplateFieldResult(column, header, value, "derived", "远程观察规则", 0.76, "远程观察离场按实际结束或 N/A"))
            continue
        if normalized == normalize_template_header("计划参会人数（不包含罗氏员工）"):
            value = facts.get("planned_attendees")
            if _is_present(value):
                results.append(facts.result(column, header, "planned_attendees"))
            else:
                results.append(default_field_result(column, header))
            continue
        if normalized == normalize_template_header("主题"):
            value = facts.get("meeting_title")
            if _is_present(value):
                results.append(facts.result(column, header, "meeting_title"))
            else:
                results.append(default_field_result(column, header))
            continue
        if normalized == normalize_template_header("本场会议是否有付费讲者和付费主席"):
            has_paid_role = bool(_safe_int(facts.get("paid_speaker_count")) or _safe_int(facts.get("paid_chair_count")))
            value = "是" if has_paid_role else "否"
            confidence = 0.72 if has_paid_role else 0.58
            evidence = "识别到付费讲者/主席人数" if has_paid_role else "未识别付费讲者/主席证据"
            results.append(TemplateFieldResult(column, header, value, "derived", "付费角色字段", confidence, evidence))
            continue
        if normalized == normalize_template_header("所有讲者姓名\n（请在括号中填写是否付费或罗氏员工）"):
            speaker = facts.get("speaker_name")
            if _is_present(speaker):
                results.append(facts.result(column, header, "speaker_name"))
            else:
                results.append(default_field_result(column, header))
            continue
        if normalized == normalize_template_header("所有主席姓名\n（是否付费或罗氏员工）"):
            chair = facts.get("meeting_chair")
            if _is_present(chair):
                results.append(facts.result(column, header, "meeting_chair", f"{chair}（是否付费待核实）"))
            else:
                results.append(TemplateFieldResult(column, header, "N/A", "not_applicable", "资料未识别付费主席", 0.45, "未识别主席付费证据"))
            continue
        if normalized == normalize_template_header("讲者和主席演讲时长（分钟）"):
            value = facts.get("speaker_service_minutes") or facts.get("planned_duration_minutes") or facts.get("actual_duration_minutes")
            if _is_present(value):
                results.append(TemplateFieldResult(column, header, value, "derived", facts.sources.get("speaker_service_minutes") or facts.sources.get("actual_duration_minutes") or "时间计算", 0.65, "讲者服务/实际时长"))
            else:
                results.append(default_field_result(column, header))
            continue
        if normalized == normalize_template_header("讲者和主席讨论时长（分钟）"):
            value = facts.get("speaker_discussion_minutes")
            if _is_present(value):
                results.append(facts.result(column, header, "speaker_discussion_minutes"))
            else:
                results.append(TemplateFieldResult(column, header, "N/A", "not_applicable", "远程观察规则", 0.72, "未识别讲者/主席讨论环节"))
            continue
        if normalized == normalize_template_header("是否有主席/讲者照片（网络/医院公示单等）\n（均有/部分有/均无/无法判断/无主席/讲者，填写N/A）"):
            value = facts.get("speaker_profile_present")
            if _is_present(value):
                results.append(facts.result(column, header, "speaker_profile_present"))
            else:
                results.append(TemplateFieldResult(column, header, "无法判断", "needs_review", "资料分类", 0.44, "未识别讲者网络资料/照片"))
            continue
        if normalized == normalize_template_header("有可疑讲者\n(是/否/无法判断/观察受限/远程填写N/A）"):
            value = "N/A" if "远程" in str(facts.get("observation_type") or "") else "否"
            results.append(TemplateFieldResult(column, header, value, "not_applicable" if value == "N/A" else "derived", "远程观察规则", 0.72, "远程观察按模板填写 N/A"))
            continue
        if normalized == normalize_template_header("现场Roche员工"):
            value = "N/A" if "远程" in str(facts.get("observation_type") or "") else "待补充/需核实"
            status = "not_applicable" if value == "N/A" else "missing"
            results.append(TemplateFieldResult(column, header, value, status, "远程观察规则", 0.72 if status == "not_applicable" else 0.0, "远程观察无现场 Roche 员工"))
            continue
        if normalized == normalize_template_header("有可疑参会人员\n(是/否/无法判断）"):
            value = "无法判断" if "远程" in str(facts.get("observation_type") or "") else "否"
            results.append(TemplateFieldResult(column, header, value, "derived", "远程观察规则", 0.58, "远程观察无法现场核验参会人身份"))
            continue
        if normalized == normalize_template_header("现场Roche员工人数"):
            value = "N/A" if "远程" in str(facts.get("observation_type") or "") else facts.get("onsite_roche_staff_count")
            if _is_present(value):
                results.append(TemplateFieldResult(column, header, value, "not_applicable" if value == "N/A" else "derived", "远程观察规则", 0.72, "远程观察无现场 Roche 员工"))
            else:
                results.append(default_field_result(column, header))
            continue
        if normalized == normalize_template_header("现场确认单发送日期\n（PMO根据活动反馈邮件的日期填写）"):
            results.append(TemplateFieldResult(column, header, "待PMO填写", "manual_required", "PMO字段", 0.0, "模板标明 PMO 根据反馈邮件日期填写"))
            continue
        if normalized == normalize_template_header("备注\n（确认书写清楚）\n参考模板"):
            value = "确认书写清楚" if facts.get("confirmation_present") else "待补充/需核实"
            status = "derived" if facts.get("confirmation_present") else "missing"
            results.append(TemplateFieldResult(column, header, value, status, "资料分类", 0.68 if status == "derived" else 0.0, "已识别现场确认单" if status == "derived" else "未识别现场确认单"))
            continue
        if normalized == normalize_template_header("暗访会议备注"):
            value = "N/A" if str(facts.get("surprise_check") or "") == "否" else "待PMO填写"
            status = "not_applicable" if value == "N/A" else "manual_required"
            results.append(TemplateFieldResult(column, header, value, status, "观察流程规则", 0.72 if status == "not_applicable" else 0.0, "非 Surprise Check/暗访会议"))
            continue
        if normalized in {normalize_template_header("累计计数"), normalize_template_header("Level9")}:
            results.append(TemplateFieldResult(column, header, "待PMO填写", "manual_required", "PMO字段", 0.0, "模板尾部内部统计字段"))
            continue
        if normalized == normalize_template_header("签到表类型（电子/纸质/电子+纸质/无签到表）"):
            if _positive_int(facts.get("actual_sign_in_count")):
                results.append(
                    TemplateFieldResult(
                        column,
                        header,
                        "电子",
                        "derived",
                        facts.sources.get("actual_sign_in_count") or "签到记录",
                        max(facts.confidence.get("actual_sign_in_count", 0.78), 0.78),
                        facts.evidence.get("actual_sign_in_count", "已识别电子签到记录"),
                    )
                )
            elif "远程" in str(facts.get("observation_type") or ""):
                results.append(TemplateFieldResult(column, header, "N/A", "not_applicable", "远程观察规则", 0.72, "未识别独立签到表，仅可按远程资料判断"))
            else:
                results.append(default_field_result(column, header))
            continue
        if normalized == normalize_template_header("签到人数（不含Roche员工）"):
            count = _positive_int(facts.get("actual_sign_in_count"))
            if count:
                results.append(facts.result(column, header, "actual_sign_in_count", count))
            elif "远程" in str(facts.get("observation_type") or ""):
                results.append(TemplateFieldResult(column, header, "N/A", "not_applicable", "远程观察规则", 0.72, "未识别可采信的签到人数"))
            else:
                results.append(default_field_result(column, header))
            continue
        if normalized in {
            normalize_template_header("存在代签\n(是/否/远程填写无法判断）"),
            normalize_template_header("存在未参会人员签到 (是/否/远程填写无法判断）"),
        }:
            if "远程" in str(facts.get("observation_type") or ""):
                results.append(TemplateFieldResult(column, header, "远程填写无法判断", "not_applicable", "远程观察规则", 0.78, "远程观察无法确认代签或未参会签到"))
            else:
                results.append(default_field_result(column, header))
            continue
        if normalized == normalize_template_header("会中最大人数（不含Roche员工）"):
            raw_max = facts.get("max_attendee_count")
            value = raw_max if _is_present(raw_max) else _positive_int(facts.get("actual_sign_in_count"))
            if _is_present(value):
                results.append(TemplateFieldResult(column, header, value, "derived", facts.sources.get("max_attendee_count") or "资料字段", 0.68, "端口人数/签到人数线索"))
            elif _is_present(facts.get("watch_record_count")):
                value = f"{facts.get('watch_record_count')}（观看记录行数，需端口截图核实）"
                results.append(TemplateFieldResult(column, header, value, "needs_review", facts.sources.get("watch_record_count") or "资料表格", 0.42, "观看记录不是端口人数，只能作为参会规模线索"))
            else:
                results.append(default_field_result(column, header))
            continue
        if normalized == normalize_template_header("开始时人数（不含Roche员工）"):
            value = facts.get("start_attendee_count")
            if _is_present(value):
                results.append(TemplateFieldResult(column, header, value, "derived", facts.sources.get("start_attendee_count") or "资料字段", 0.68, "开始时端口人数"))
            else:
                results.append(default_field_result(column, header))
            continue
        if normalized == normalize_template_header("结束时人数（不含Roche员工）"):
            value = facts.get("end_attendee_count")
            if _is_present(value):
                results.append(TemplateFieldResult(column, header, value, "derived", facts.sources.get("end_attendee_count") or "资料字段", 0.68, "结束时端口人数"))
            else:
                results.append(default_field_result(column, header))
            continue
        if normalized == normalize_template_header("PPT主题及编码"):
            topic = facts.get("presentation_topic")
            code = facts.get("material_code_display") or facts.get("material_code")
            value = f"{topic}\n{code}" if _is_present(topic) and _is_present(code) else code or topic
            if _is_present(value):
                source_key = "material_code" if _is_present(code) else "presentation_topic"
                results.append(facts.result(column, header, source_key, value))
            else:
                results.append(default_field_result(column, header))
            continue
        if normalized == normalize_template_header("其他可疑情况\n（是，否，远程填写无法判断）"):
            value = "是" if facts.get("other_company_seen") == "是" else "否"
            results.append(TemplateFieldResult(column, header, value, "derived", "资料文本", 0.56, "其他厂家线索" if value == "是" else "未识别其他可疑情况"))
            continue

        results.append(default_field_result(column, header))

    return results
