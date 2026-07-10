from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from PIL import Image, ImageOps

from app.services.domain.compliance.material_vision_skill import (
    HANDWRITING_CATEGORIES,
    build_material_vision_profile,
    build_vision_consensus,
)
from app.config import settings
from app.services.vision_client import vision_analyze_image, vision_available, vision_fields_to_text

DEFAULT_PROMPT = """你是罗氏会议合规远程观察的视觉分析专员。请阅读图片并输出 JSON（不要 markdown）：
{
  "summary_text": "图片内容摘要",
  "reasoning": "合规相关推理（80字内）",
  "confidence": 0.0,
  "speaker_name": "",
  "speaker_service_minutes": 0,
  "material_code": "",
  "planned_attendees": 0,
  "actual_sign_in_count": 0,
  "actual_duration_minutes": 0,
  "meeting_code": "",
  "observation_success": "",
  "key_facts": []
}
无法确认的字段留空或 0；confidence 为 0-1。"""

CATEGORY_PROMPTS: Dict[str, str] = {
    "observation_confirmation": """你是远程观察「现场确认单/观察记录确认书」视觉专员。读图并输出 JSON：
字段：summary_text, reasoning, confidence, meeting_code, observation_success（是/否）,
actual_date, actual_start_time, actual_end_time, actual_platform（如 ZOOM/会议号）,
start_attendee_count, max_attendee_count, end_attendee_count（可保留组合原文，如 7+46人次）,
speaker_name, speaker_service_minutes（含讨论共计分钟）, actual_duration_minutes,
presentation_topic, material_code（P-/NP-/M-CN-/Promotional-，会议编号不是材料编码）, ppt_pages。
手写字段要逐项读取；无法确认的字段留空，不要用单张参会者截图数替代确认单人数。""",
    "sign_in_record": """你是「签到表/签到列表」视觉专员。读图并输出 JSON：
字段：summary_text, reasoning, confidence, actual_sign_in_count（已签到人数）, planned_attendees, meeting_code""",
    "coordination_sms": """你是「远程观察沟通短信/微信截图」视觉专员。读图并输出 JSON：
字段：summary_text, reasoning, confidence, meeting_code, key_facts（数组，列出观察时间/会议编码等）""",
    "meeting_screenshot": """你是「线上会议平台截图」视觉专员。读图并输出 JSON：
字段：summary_text, reasoning, confidence, actual_platform（如 ZOOM 会议号/直播平台）,
start_attendee_count, max_attendee_count, end_attendee_count, speaker_name, actual_duration_minutes,
key_facts（是否在演讲、参会人数线索等）。人数可保留截图原文，例如 5+61人次；无法确认留空。""",
    "presentation_material": """你是「演讲 PPT/材料截图」视觉专员。读图并输出 JSON：
字段：summary_text, reasoning, confidence, presentation_topic, material_code, ppt_pages, speaker_name, key_facts""",
    "meeting_agenda": """你是「会议议程」视觉专员。读图并输出 JSON：
字段：summary_text, reasoning, confidence, planned_duration_minutes, planned_attendees, meeting_code""",
    "speaker_profile": """你是「讲者公开资料/网络截图」视觉专员。读图并输出 JSON：
字段：summary_text, reasoning, confidence, speaker_name, key_facts""",
    "other_supporting_evidence": """你是「其他支持证据」视觉专员。读图并输出 JSON：
字段：summary_text, reasoning, confidence, actual_sponsor, other_company_seen（是/否/无法判断）,
other_company_name, key_facts（列出厂家、赞助回报、品牌露出、会议支持或其他合规相关事实）""",
}

PRESENTATION_CROP_PROMPT = """你是远程观察 PPT 材料页脚识别专员。请只识别这张裁剪图中的材料编码和主题，输出 JSON：
{
  "summary_text": "裁剪区域可见文字",
  "confidence": 0.0,
  "presentation_topic": "",
  "material_code": "",
  "ppt_pages": 0
}
材料编码只能是 P-/NP-/M-CN-/Promotional- 形式；会议编号如 SMS/A1P 不是材料编码。
如果看到“幻灯片 1/30”或“Slide 1/30”，ppt_pages 必须填总页数 30，而不是当前页 1。无法确认留空。"""

SECOND_PASS_PROMPT_PREFIX = """这是同一份高风险观察资料的第二轮独立复核。
不要引用第一轮结论；请重新读图，只输出 JSON。
重点核对手写/签名/人数/时间/会议编码等字段。如果不确定，字段留空并降低 confidence。
"""


def _coerce_float(val: Any) -> float | None:
    if val in (None, ""):
        return None
    try:
        return float(str(val).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _coerce_int(val: Any) -> int | None:
    f = _coerce_float(val)
    if f is None:
        return None
    return int(f)


def _stringify_for_search(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


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


def _material_code_from_payload(data: Dict[str, Any]) -> str:
    for key in ("material_code", "summary_text", "raw_text", "text_content", "md_results", "reasoning", "key_facts"):
        material_code = _valid_material_code(_stringify_for_search(data.get(key)))
        if material_code:
            return material_code
    return ""


def _field_confidence_from_fields(fields: Dict[str, Any]) -> Dict[str, float]:
    conf = _coerce_float(fields.get("vision_confidence") or fields.get("confidence")) or 0.0
    return {key: conf for key in fields if key not in {"key_facts"}}


def _vision_candidate(pass_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pass_id": pass_id,
        "fields": fields,
        "field_confidence": _field_confidence_from_fields(fields),
    }


def _high_risk_min_passes(document_category: str) -> int:
    if document_category not in HANDWRITING_CATEGORIES:
        return 1
    return max(1, int(getattr(settings, "vision_high_risk_min_passes", 2) or 1))


def _second_pass_prompt(document_category: str, file_name: str = "") -> str:
    base = CATEGORY_PROMPTS.get(document_category) or DEFAULT_PROMPT
    prefix = f"文件名：{file_name}\n资料类型：{document_category}\n\n" if file_name else ""
    return f"{prefix}{SECOND_PASS_PROMPT_PREFIX}\n{base}"


def _secondary_candidate_from_raw(raw: Dict[str, Any], document_category: str) -> Dict[str, Any]:
    fields = normalize_compliance_vision(raw, document_category)
    return _vision_candidate("independent_second_pass", fields)


def _crop_specs_for_presentation(image: Image.Image) -> list[tuple[str, tuple[int, int, int, int]]]:
    width, height = image.size
    return [
        ("slide_count_status_bar", (0, int(height * 0.60), int(width * 0.42), int(height * 0.67))),
        ("slide_thumbnail_pane", (0, int(height * 0.34), int(width * 0.26), int(height * 0.68))),
        ("mid_lower_band", (0, int(height * 0.48), width, int(height * 0.78))),
        ("slide_footer_band", (0, int(height * 0.58), width, int(height * 0.76))),
        ("lower_half", (0, int(height * 0.42), width, int(height * 0.86))),
    ]


def _prepare_crop_for_ocr(image: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    left, top, right, bottom = box
    crop = image.crop((left, top, right, bottom)).convert("RGB")
    scale = 2 if max(crop.size) >= 1800 else 3
    crop = crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.LANCZOS)
    return ImageOps.autocontrast(crop)


def _recover_presentation_fields_from_crops(
    fields: Dict[str, Any],
    *,
    image: Image.Image | None,
    file_name: str = "",
    on_retry: Optional[Callable[[int, int, float, str], None]] = None,
) -> list[dict[str, Any]]:
    pages = _coerce_int(fields.get("ppt_pages"))
    needs_page_recovery = pages is None or pages <= 1
    needs_topic_recovery = not fields.get("presentation_topic") or _coerce_float(fields.get("vision_confidence")) < 0.8
    needs_code_recovery = not fields.get("material_code")
    if image is None or not (needs_code_recovery or needs_page_recovery or needs_topic_recovery):
        return []

    from app.services.vision_client import vision_analyze_pil_image, vision_available

    if not vision_available():
        return []

    recoveries: list[dict[str, Any]] = []
    prompt = f"文件名：{file_name}\n\n{PRESENTATION_CROP_PROMPT}" if file_name else PRESENTATION_CROP_PROMPT
    for crop_name, box in _crop_specs_for_presentation(image):
        try:
            crop = _prepare_crop_for_ocr(image, box)
            raw = vision_analyze_pil_image(crop, prompt=prompt, on_retry=on_retry)
        except Exception:
            continue
        recovered = normalize_compliance_vision(raw, "presentation_material")
        for field_name in ("material_code", "presentation_topic", "ppt_pages"):
            recovered_value = recovered.get(field_name)
            should_replace = fields.get(field_name) in (None, "", 0)
            if field_name == "ppt_pages":
                current_pages = _coerce_int(fields.get("ppt_pages"))
                recovered_pages = _coerce_int(recovered_value)
                should_replace = bool(recovered_pages and (current_pages is None or recovered_pages > current_pages))
                recovered_value = recovered_pages
            if field_name == "presentation_topic":
                should_replace = should_replace or (
                    bool(recovered_value)
                    and (_coerce_float(recovered.get("vision_confidence")) or 0.0)
                    >= (_coerce_float(fields.get("vision_confidence")) or 0.0)
                    and len(str(recovered_value)) > len(str(fields.get(field_name) or ""))
                )
            if should_replace and recovered_value not in (None, "", 0):
                fields[field_name] = recovered_value
                recoveries.append(
                    {
                        "field": field_name,
                        "value": recovered_value,
                        "source": f"crop:{crop_name}",
                        "confidence": recovered.get("vision_confidence") or 0.72,
                    }
                )
        current_pages = _coerce_int(fields.get("ppt_pages"))
        if fields.get("material_code") and current_pages and current_pages > 1 and fields.get("presentation_topic"):
            break
    if recoveries:
        fields["vision_crop_recovery"] = recoveries
    return recoveries


def normalize_compliance_vision(data: Dict[str, Any], document_category: str) -> Dict[str, Any]:
    fields: Dict[str, Any] = {
        "document_category": document_category,
        "summary_text": data.get("summary_text") or data.get("raw_text") or "",
        "vision_reasoning": data.get("reasoning") or "",
        "vision_confidence": _coerce_float(data.get("confidence")) or 0.0,
        "speaker_name": data.get("speaker_name") or "",
        "meeting_code": data.get("meeting_code") or "",
        "observation_success": data.get("observation_success") or "",
        "key_facts": data.get("key_facts") or [],
    }
    material_code = _material_code_from_payload(data)
    if material_code:
        fields["material_code"] = material_code
    for key in (
        "speaker_service_minutes",
        "planned_attendees",
        "actual_sign_in_count",
        "actual_duration_minutes",
        "planned_duration_minutes",
        "ppt_pages",
        "paid_speaker_count",
        "paid_chair_count",
    ):
        iv = _coerce_int(data.get(key))
        if iv is not None:
            fields[key] = iv
    if "ppt_pages" not in fields:
        text_for_pages = _stringify_for_search(data)
        page_match = re.search(r"(?:幻灯片|slide)[^\d]{0,10}\d{1,3}\s*/\s*(\d{1,3})", text_for_pages, re.I)
        if page_match:
            fields["ppt_pages"] = int(page_match.group(1))
    for key in (
        "presentation_topic",
        "actual_platform",
        "actual_date",
        "actual_start_time",
        "actual_end_time",
        "start_attendee_count",
        "max_attendee_count",
        "end_attendee_count",
        "actual_sponsor",
        "other_company_seen",
        "other_company_name",
    ):
        val = data.get(key)
        if val not in (None, "", [], {}):
            fields[key] = val
    return fields


def analyze_compliance_image(
    file_path: Path,
    document_category: str,
    file_name: str = "",
    *,
    on_retry: Optional[Callable[[int, int, float, str], None]] = None,
) -> Dict[str, Any]:
    """GLM-OCR / 视觉 Agent：OCR 读图 + 文本 LLM 结构化抽取，返回与 parse_image 兼容的结构。"""
    return _analyze_compliance_vision_source(
        file_path=file_path,
        document_category=document_category,
        file_name=file_name,
        on_retry=on_retry,
    )


def analyze_compliance_pil_image(
    image,
    document_category: str,
    file_name: str = "",
    *,
    on_retry: Optional[Callable[[int, int, float, str], None]] = None,
) -> Dict[str, Any]:
    """PDF 页或内嵌图转 PIL 后走合规视觉结构化解析。"""
    from app.services.vision_client import vision_analyze_pil_image, vision_available
    from app.services.ocr_service import ocr_pil_image

    prompt = CATEGORY_PROMPTS.get(document_category) or DEFAULT_PROMPT
    if file_name:
        prompt = f"文件名：{file_name}\n资料类型：{document_category}\n\n{prompt}"

    if not vision_available():
        text, ocr_engine = ocr_pil_image(image)
        fields = normalize_compliance_vision({"summary_text": text, "confidence": 0.5}, document_category)
        return _with_vision_reliability_profile(
            {
                "file_type": "image",
                "document_type": document_category,
                "ocr_engine": ocr_engine,
                "text_content": text,
                "fields": fields,
                "confidence": {k: fields.get("vision_confidence", 0.5) for k in fields},
                "bbox": [],
                "vision_agent": True,
            },
            image=image,
            document_category=document_category,
            file_name=file_name,
        )

    raw = vision_analyze_pil_image(image, prompt=prompt, on_retry=on_retry)
    additional_candidates: list[dict[str, Any]] = []
    if _high_risk_min_passes(document_category) >= 2:
        try:
            second_raw = vision_analyze_pil_image(
                image,
                prompt=_second_pass_prompt(document_category, file_name),
                on_retry=on_retry,
            )
            additional_candidates.append(_secondary_candidate_from_raw(second_raw, document_category))
        except Exception:
            additional_candidates = []
    return _compliance_content_from_raw(
        raw,
        document_category,
        image=image,
        file_name=file_name,
        additional_candidates=additional_candidates,
    )


def _with_vision_reliability_profile(
    content: Dict[str, Any],
    *,
    image: Image.Image | None,
    document_category: str,
    file_name: str = "",
) -> Dict[str, Any]:
    fields = content.get("fields") or {}
    profile = build_material_vision_profile(
        image=image,
        document_category=document_category,
        file_name=file_name,
        fields=fields,
        raw_text=content.get("text_content") or fields.get("summary_text") or "",
    )
    fields["vision_manual_review_required"] = profile["manual_review_required"]
    fields["vision_review_reasons"] = profile["review_reasons"]
    content["fields"] = fields
    content["manual_review_required"] = profile["manual_review_required"]
    content["review_reasons"] = profile["review_reasons"]
    content["vision_quality"] = profile["quality"]
    content["recognition_plan"] = profile["recognition_plan"]
    content["field_confidence"] = profile["field_confidence"]

    primary_candidate = {
        "pass_id": content.get("ocr_engine") or "primary_vision_pass",
        "fields": fields,
        "field_confidence": profile["field_confidence"],
    }
    raw_candidates = content.get("vision_candidates")
    candidates = raw_candidates if isinstance(raw_candidates, list) and raw_candidates else [primary_candidate]
    consensus = build_vision_consensus(
        document_category=document_category,
        candidates=candidates,
    )
    content["vision_consensus"] = consensus
    fields["vision_consensus_status"] = consensus["status"]
    fields["vision_consensus_review_reasons"] = consensus["review_reasons"]
    if consensus["manual_review_required"]:
        content["manual_review_required"] = True
        fields["vision_manual_review_required"] = True
        content["review_reasons"] = list(
            dict.fromkeys([*content.get("review_reasons", []), *consensus["review_reasons"]])
        )
        fields["vision_review_reasons"] = content["review_reasons"]

    confidence = content.get("confidence") or {}
    if isinstance(confidence, dict):
        merged_confidence = dict(confidence)
        for key, value in profile["field_confidence"].items():
            current = merged_confidence.get(key)
            if current is None:
                merged_confidence[key] = value
            else:
                try:
                    merged_confidence[key] = min(float(current), float(value))
                except (TypeError, ValueError):
                    merged_confidence[key] = value
        content["confidence"] = merged_confidence
    return content


def _compliance_content_from_raw(
    raw: Dict[str, Any],
    document_category: str,
    *,
    image: Image.Image | None = None,
    file_name: str = "",
    additional_candidates: list[dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    fields = normalize_compliance_vision(raw, document_category)
    crop_recoveries: list[dict[str, Any]] = []
    if document_category == "presentation_material":
        crop_recoveries = _recover_presentation_fields_from_crops(
            fields,
            image=image,
            file_name=file_name,
        )
    text = vision_fields_to_text(raw) or fields.get("summary_text") or ""
    if crop_recoveries:
        text = f"{text}\n裁剪复核：{_stringify_for_search(crop_recoveries)}".strip()
    if fields.get("vision_reasoning"):
        text = f"{text}\n推理：{fields['vision_reasoning']}".strip()

    conf_base = fields.get("vision_confidence") or 0.85
    vision_candidates = [_vision_candidate("primary_vision_pass", fields)]
    if additional_candidates:
        vision_candidates.extend(additional_candidates)
    return _with_vision_reliability_profile(
        {
            "file_type": "image",
            "document_type": document_category,
            "ocr_engine": f"vision:{raw.get('_model', 'glm-ocr')}",
            "text_content": text,
            "fields": fields,
            "confidence": {k: conf_base for k in fields if k not in ("key_facts",)},
            "bbox": [],
            "vision_agent": True,
            "vision_raw": {k: v for k, v in raw.items() if k != "_model"},
            "vision_candidates": vision_candidates,
        },
        image=image,
        document_category=document_category,
        file_name=file_name,
    )


def _analyze_compliance_vision_source(
    *,
    file_path: Path,
    document_category: str,
    file_name: str = "",
    on_retry: Optional[Callable[[int, int, float, str], None]] = None,
) -> Dict[str, Any]:
    prompt = CATEGORY_PROMPTS.get(document_category) or DEFAULT_PROMPT
    if file_name:
        prompt = f"文件名：{file_name}\n资料类型：{document_category}\n\n{prompt}"

    if not vision_available():
        from app.services.ocr_service import ocr_image_file

        text, ocr_engine = ocr_image_file(file_path)
        fields = normalize_compliance_vision({"summary_text": text, "confidence": 0.5}, document_category)
        try:
            image = Image.open(file_path).convert("RGB")
        except Exception:
            image = None
        return _with_vision_reliability_profile(
            {
                "file_type": "image",
                "document_type": document_category,
                "ocr_engine": ocr_engine,
                "text_content": text,
                "fields": fields,
                "confidence": {k: fields.get("vision_confidence", 0.5) for k in fields},
                "bbox": [],
                "vision_agent": True,
            },
            image=image,
            document_category=document_category,
            file_name=file_name,
        )

    raw = vision_analyze_image(file_path, prompt=prompt, on_retry=on_retry)
    additional_candidates: list[dict[str, Any]] = []
    if _high_risk_min_passes(document_category) >= 2:
        try:
            second_raw = vision_analyze_image(
                file_path,
                prompt=_second_pass_prompt(document_category, file_name),
                on_retry=on_retry,
            )
            additional_candidates.append(_secondary_candidate_from_raw(second_raw, document_category))
        except Exception:
            additional_candidates = []
    try:
        image = Image.open(file_path).convert("RGB")
    except Exception:
        image = None
    return _compliance_content_from_raw(
        raw,
        document_category,
        image=image,
        file_name=file_name,
        additional_candidates=additional_candidates,
    )


def merge_vision_into_parsed_doc(content: dict) -> dict:
    """供 build_case_facts 使用的扁平字段。"""
    fields = content.get("fields") or {}
    if isinstance(fields, dict) and fields.get("vision_reasoning"):
        content.setdefault("vision_reasoning", fields["vision_reasoning"])
    return content
