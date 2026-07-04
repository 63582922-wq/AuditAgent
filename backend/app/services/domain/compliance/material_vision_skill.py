from __future__ import annotations

from typing import Any, Dict, Iterable, List

from PIL import Image, ImageFilter, ImageStat

HANDWRITING_CATEGORIES = {"observation_confirmation", "sign_in_record"}

HANDWRITING_KEYWORDS = (
    "手写",
    "签名",
    "签字",
    "签署",
    "到场确认",
    "现场确认",
    "确认单",
    "观察确认",
    "签到",
)

TARGET_FIELDS: Dict[str, List[str]] = {
    "observation_confirmation": [
        "meeting_code",
        "actual_date",
        "actual_start_time",
        "actual_end_time",
        "actual_platform",
        "start_attendee_count",
        "max_attendee_count",
        "end_attendee_count",
        "speaker_name",
        "speaker_service_minutes",
        "actual_duration_minutes",
        "observation_success",
        "presentation_topic",
        "material_code",
        "ppt_pages",
        "signature_or_written_confirmation",
    ],
    "sign_in_record": [
        "meeting_code",
        "actual_sign_in_count",
        "planned_attendees",
        "signature_or_written_confirmation",
    ],
    "coordination_sms": ["meeting_code", "key_facts"],
    "meeting_screenshot": [
        "actual_platform",
        "start_attendee_count",
        "max_attendee_count",
        "end_attendee_count",
        "speaker_name",
        "actual_duration_minutes",
        "key_facts",
    ],
    "presentation_material": ["presentation_topic", "material_code", "ppt_pages", "speaker_name", "key_facts"],
    "meeting_agenda": ["meeting_code", "planned_duration_minutes", "planned_attendees"],
    "speaker_profile": ["speaker_name", "key_facts"],
    "other_supporting_evidence": ["actual_sponsor", "other_company_seen", "other_company_name", "key_facts"],
}

REQUIRED_FIELDS: Dict[str, List[str]] = {
    "observation_confirmation": [
        "meeting_code",
        "speaker_service_minutes",
        "observation_success",
    ],
    "sign_in_record": ["actual_sign_in_count"],
    "meeting_screenshot": ["speaker_name", "actual_duration_minutes"],
}


def _coerce_confidence(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return default


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _normalize_consensus_value(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.strip().split()).lower()
    return str(value)


def _candidate_confidence(candidate: Dict[str, Any], field: str) -> float:
    confidence = candidate.get("field_confidence")
    if isinstance(confidence, dict) and field in confidence:
        return _coerce_confidence(confidence.get(field), 0.0)
    fields = candidate.get("fields")
    if isinstance(fields, dict):
        return _coerce_confidence(
            fields.get("vision_confidence") or fields.get("confidence"),
            0.0,
        )
    return _coerce_confidence(candidate.get("confidence"), 0.0)


def _haystack(*parts: Any) -> str:
    return " ".join(str(p or "") for p in parts).lower()


def assess_image_quality(image: Image.Image | None) -> Dict[str, Any]:
    if image is None:
        return {
            "width": None,
            "height": None,
            "score": 0.65,
            "flags": ["image_not_available_for_quality_check"],
            "metrics": {},
        }

    rgb = image.convert("RGB")
    width, height = rgb.size
    gray = rgb.convert("L")
    stat = ImageStat.Stat(gray)
    contrast = float(stat.stddev[0])
    edge = gray.filter(ImageFilter.FIND_EDGES)
    edge_strength = float(ImageStat.Stat(edge).mean[0])

    flags: List[str] = []
    score = 1.0
    pixels = width * height
    aspect_ratio = max(width, height) / max(min(width, height), 1)

    if min(width, height) < 600 or pixels < 500_000:
        flags.append("low_resolution")
        score -= 0.32
    if aspect_ratio >= 3.2 and max(width, height) >= 2500:
        flags.append("long_image_needs_slicing")
        score -= 0.12
    if contrast < 22.0:
        flags.append("low_contrast")
        score -= 0.24
    if edge_strength < 1.0:
        flags.append("blur_or_low_detail")
        score -= 0.18

    return {
        "width": width,
        "height": height,
        "score": round(max(0.0, min(score, 1.0)), 2),
        "flags": flags,
        "metrics": {
            "pixels": pixels,
            "aspect_ratio": round(aspect_ratio, 2),
            "contrast_stddev": round(contrast, 2),
            "edge_strength": round(edge_strength, 2),
        },
    }


def _target_fields(document_category: str) -> List[str]:
    return list(TARGET_FIELDS.get(document_category) or ["summary_text", "key_facts"])


def _required_fields(document_category: str) -> List[str]:
    return list(REQUIRED_FIELDS.get(document_category) or [])


def build_vision_consensus(
    *,
    document_category: str,
    candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge multiple OCR/vision passes and mark disagreements before audit rules consume them."""
    target_fields = _target_fields(document_category)
    required_fields = _required_fields(document_category)
    all_fields = list(
        dict.fromkeys(
            target_fields
            + [
                field
                for candidate in candidates
                for field in ((candidate.get("fields") or {}).keys() if isinstance(candidate.get("fields"), dict) else [])
            ]
        )
    )

    merged_fields: Dict[str, Any] = {}
    field_confidence: Dict[str, float] = {}
    conflicts: List[Dict[str, Any]] = []
    missing_required: List[str] = []

    if not candidates:
        return {
            "status": "needs_review",
            "manual_review_required": True,
            "review_reasons": ["no_vision_candidates"],
            "fields": {},
            "field_confidence": {},
            "conflicts": [],
            "candidate_count": 0,
            "target_fields": target_fields,
            "required_fields": required_fields,
        }

    for field in all_fields:
        values: List[Dict[str, Any]] = []
        for index, candidate in enumerate(candidates):
            fields = candidate.get("fields") if isinstance(candidate.get("fields"), dict) else {}
            value = fields.get(field)
            if not _is_present(value):
                continue
            values.append(
                {
                    "pass_id": candidate.get("pass_id") or f"pass_{index + 1}",
                    "value": value,
                    "confidence": _candidate_confidence(candidate, field),
                }
            )

        if not values:
            if field in required_fields:
                missing_required.append(field)
                merged_fields[field] = None
                field_confidence[field] = 0.0
            continue

        unique_values = {_normalize_consensus_value(item["value"]) for item in values}
        if len(unique_values) > 1:
            conflicts.append({"field": field, "values": values})
            merged_fields[field] = None
            field_confidence[field] = round(min(0.45, min(item["confidence"] for item in values)), 2)
            continue

        best = max(values, key=lambda item: item["confidence"])
        merged_fields[field] = best["value"]
        field_confidence[field] = round(min(item["confidence"] for item in values), 2)

    review_reasons: List[str] = []
    if conflicts:
        review_reasons.append("vision_consensus_conflict")
    if missing_required:
        review_reasons.append("missing_required_fields")
    if len(candidates) == 1 and document_category in HANDWRITING_CATEGORIES:
        review_reasons.append("single_pass_high_risk_document")

    manual_review_required = bool(review_reasons)
    return {
        "status": "needs_review" if manual_review_required else "accepted",
        "manual_review_required": manual_review_required,
        "review_reasons": review_reasons,
        "fields": merged_fields,
        "field_confidence": field_confidence,
        "conflicts": conflicts,
        "missing_required_fields": missing_required,
        "candidate_count": len(candidates),
        "target_fields": target_fields,
        "required_fields": required_fields,
    }


def _detect_handwriting_risk(
    *,
    document_category: str,
    file_name: str,
    fields: Dict[str, Any],
    raw_text: str,
) -> bool:
    text = _haystack(file_name, raw_text, fields.get("summary_text"), fields.get("vision_reasoning"))
    if any(keyword.lower() in text for keyword in HANDWRITING_KEYWORDS):
        return True
    return document_category in HANDWRITING_CATEGORIES and any(
        not _is_present(fields.get(field))
        for field in _required_fields(document_category)
    )


def _field_confidence(
    *,
    fields: Dict[str, Any],
    target_fields: Iterable[str],
    base_confidence: float,
    quality_score: float,
    handwriting_risk: bool,
) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for field in target_fields:
        if field == "signature_or_written_confirmation":
            present = handwriting_risk
        else:
            present = _is_present(fields.get(field))

        confidence = min(base_confidence, quality_score)
        if not present:
            confidence = min(confidence, 0.45)
        if handwriting_risk and field in {
            "speaker_service_minutes",
            "actual_duration_minutes",
            "observation_success",
            "signature_or_written_confirmation",
        }:
            confidence = min(confidence, 0.68)
        out[field] = round(max(0.0, min(confidence, 1.0)), 2)
    return out


def build_material_vision_profile(
    *,
    image: Image.Image | None,
    document_category: str,
    file_name: str = "",
    fields: Dict[str, Any] | None = None,
    raw_text: str = "",
) -> Dict[str, Any]:
    fields = fields or {}
    quality = assess_image_quality(image)
    base_confidence = _coerce_confidence(fields.get("vision_confidence") or fields.get("confidence"), 0.0)
    target_fields = _target_fields(document_category)
    handwriting_risk = _detect_handwriting_risk(
        document_category=document_category,
        file_name=file_name,
        fields=fields,
        raw_text=raw_text,
    )

    review_reasons: List[str] = list(quality["flags"])
    if handwriting_risk:
        review_reasons.append("handwriting_risk")
    if base_confidence and base_confidence < 0.8:
        review_reasons.append("low_model_confidence")

    missing_required = [
        field for field in _required_fields(document_category) if not _is_present(fields.get(field))
    ]
    if missing_required:
        review_reasons.append("missing_required_fields")

    field_confidence = _field_confidence(
        fields=fields,
        target_fields=target_fields,
        base_confidence=base_confidence or 0.6,
        quality_score=quality["score"],
        handwriting_risk=handwriting_risk,
    )

    passes = ["layout_ocr"]
    if quality["flags"]:
        passes.append("image_enhancement")
    if "long_image_needs_slicing" in quality["flags"]:
        passes.append("long_image_slicing")
    if handwriting_risk or document_category in HANDWRITING_CATEGORIES:
        passes.extend(["field_crop_ocr", "handwriting_focused_pass"])
    if document_category in HANDWRITING_CATEGORIES or missing_required:
        passes.append("cross_evidence_check")
    passes = list(dict.fromkeys(passes))

    required_low_confidence = any(
        field_confidence.get(field, 0.0) < 0.7 for field in _required_fields(document_category)
    )
    manual_review_required = bool(
        quality["flags"]
        or handwriting_risk
        or (base_confidence and base_confidence < 0.8)
        or missing_required
        or required_low_confidence
    )

    return {
        "skill": "material_vision_accuracy",
        "document_category": document_category,
        "manual_review_required": manual_review_required,
        "review_reasons": list(dict.fromkeys(review_reasons)),
        "quality": quality,
        "field_confidence": field_confidence,
        "recognition_plan": {
            "strategy": "multi_pass_field_ocr" if manual_review_required else "standard_vision_ocr",
            "passes": passes,
            "target_fields": target_fields,
            "missing_required_fields": missing_required,
            "requires_human_review": manual_review_required,
        },
    }
