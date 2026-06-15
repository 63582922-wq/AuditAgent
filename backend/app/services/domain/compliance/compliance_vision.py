from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

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
字段：summary_text, reasoning, confidence, speaker_name, speaker_service_minutes（含讨论共计分钟）,
material_code（M-CN- 或 Promotional）, actual_duration_minutes, meeting_code, observation_success（是/否）""",
    "sign_in_record": """你是「签到表/签到列表」视觉专员。读图并输出 JSON：
字段：summary_text, reasoning, confidence, actual_sign_in_count（已签到人数）, planned_attendees, meeting_code""",
    "coordination_sms": """你是「远程观察沟通短信/微信截图」视觉专员。读图并输出 JSON：
字段：summary_text, reasoning, confidence, meeting_code, key_facts（数组，列出观察时间/会议编码等）""",
    "meeting_screenshot": """你是「线上会议平台截图」视觉专员。读图并输出 JSON：
字段：summary_text, reasoning, confidence, speaker_name, actual_duration_minutes,
key_facts（是否在演讲、参会人数线索等）""",
    "presentation_material": """你是「演讲 PPT/材料截图」视觉专员。读图并输出 JSON：
字段：summary_text, reasoning, confidence, material_code, speaker_name, key_facts""",
    "meeting_agenda": """你是「会议议程」视觉专员。读图并输出 JSON：
字段：summary_text, reasoning, confidence, planned_duration_minutes, planned_attendees, meeting_code""",
    "speaker_profile": """你是「讲者公开资料/网络截图」视觉专员。读图并输出 JSON：
字段：summary_text, reasoning, confidence, speaker_name, key_facts""",
}


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


def normalize_compliance_vision(data: Dict[str, Any], document_category: str) -> Dict[str, Any]:
    fields: Dict[str, Any] = {
        "document_category": document_category,
        "summary_text": data.get("summary_text") or data.get("raw_text") or "",
        "vision_reasoning": data.get("reasoning") or "",
        "vision_confidence": _coerce_float(data.get("confidence")) or 0.0,
        "speaker_name": data.get("speaker_name") or "",
        "material_code": data.get("material_code") or "",
        "meeting_code": data.get("meeting_code") or "",
        "observation_success": data.get("observation_success") or "",
        "key_facts": data.get("key_facts") or [],
    }
    for key in (
        "speaker_service_minutes",
        "planned_attendees",
        "actual_sign_in_count",
        "actual_duration_minutes",
        "planned_duration_minutes",
    ):
        iv = _coerce_int(data.get(key))
        if iv is not None:
            fields[key] = iv
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
        return {
            "file_type": "image",
            "document_type": document_category,
            "ocr_engine": ocr_engine,
            "text_content": text,
            "fields": fields,
            "confidence": {k: fields.get("vision_confidence", 0.5) for k in fields},
            "bbox": [],
            "vision_agent": True,
        }

    raw = vision_analyze_pil_image(image, prompt=prompt, on_retry=on_retry)
    return _compliance_content_from_raw(raw, document_category)


def _compliance_content_from_raw(raw: Dict[str, Any], document_category: str) -> Dict[str, Any]:
    fields = normalize_compliance_vision(raw, document_category)
    text = vision_fields_to_text(raw) or fields.get("summary_text") or ""
    if fields.get("vision_reasoning"):
        text = f"{text}\n推理：{fields['vision_reasoning']}".strip()

    conf_base = fields.get("vision_confidence") or 0.85
    return {
        "file_type": "image",
        "document_type": document_category,
        "ocr_engine": f"vision:{raw.get('_model', 'glm-ocr')}",
        "text_content": text,
        "fields": fields,
        "confidence": {k: conf_base for k in fields if k not in ("key_facts",)},
        "bbox": [],
        "vision_agent": True,
        "vision_raw": {k: v for k, v in raw.items() if k != "_model"},
    }


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
        return {
            "file_type": "image",
            "document_type": document_category,
            "ocr_engine": ocr_engine,
            "text_content": text,
            "fields": fields,
            "confidence": {k: fields.get("vision_confidence", 0.5) for k in fields},
            "bbox": [],
            "vision_agent": True,
        }

    raw = vision_analyze_image(file_path, prompt=prompt, on_retry=on_retry)
    return _compliance_content_from_raw(raw, document_category)


def merge_vision_into_parsed_doc(content: dict) -> dict:
    """供 build_case_facts 使用的扁平字段。"""
    fields = content.get("fields") or {}
    if isinstance(fields, dict) and fields.get("vision_reasoning"):
        content.setdefault("vision_reasoning", fields["vision_reasoning"])
    return content
