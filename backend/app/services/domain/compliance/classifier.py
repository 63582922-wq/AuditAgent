from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

from app.services.domain.compliance.constants import CATEGORY_KEYWORDS
from app.services.domain.compliance.llm_classify import maybe_llm_classify


def classify_compliance_document(file_name: str, ext: str, text: str = "") -> Dict[str, Any]:
    lower = file_name.lower()
    scores: Dict[str, float] = {}
    ext_map = {
        ".xlsx": "excel", ".xls": "excel", ".csv": "excel",
        ".docx": "word", ".doc": "word",
        ".pdf": "pdf", ".jpg": "image", ".jpeg": "image", ".png": "image",
    }
    file_type = ext_map.get(ext.lower(), "unknown")

    for category, keywords in CATEGORY_KEYWORDS.items():
        hit = 0
        for kw in keywords:
            kw_lower = kw.lower()
            # FX supporting images often carry the case code in every filename.
            # That code identifies the meeting, not the evidence type.
            if file_type == "image" and kw_lower == "a1p":
                continue
            if kw_lower in lower:
                hit += 1
        if hit:
            scores[category] = min(0.65 + hit * 0.2, 0.98)

    confirmation_name = bool(re.search(r"确认单|现场确认|观察记录|确认书|观察确认", file_name, re.I))
    if file_type == "image" and confirmation_name:
        scores["observation_confirmation"] = max(scores.get("observation_confirmation", 0), 0.97)
    if re.search(r"a1p\d+", lower) and file_type in {"pdf", "excel"}:
        scores["a1_meeting_export"] = max(scores.get("a1_meeting_export", 0), 0.95)
    if "supporting" in lower:
        scores["observation_confirmation"] = scores.get("observation_confirmation", 0) + 0.1

    sample = (text or "")[:8000]
    if sample:
        if "A1 Platform" in sample or (file_type in {"pdf", "excel"} and "会议编号" in sample):
            scores["a1_meeting_export"] = max(scores.get("a1_meeting_export", 0), 0.9)
        if "观察记录确认书" in sample or "现场确认" in sample:
            scores["observation_confirmation"] = max(scores.get("observation_confirmation", 0), 0.9)
        if "签到列表" in sample or "签到时间" in sample:
            scores["sign_in_record"] = max(scores.get("sign_in_record", 0), 0.85)
        if "会议日程" in sample and "环节类型" in sample:
            scores["meeting_agenda"] = max(scores.get("meeting_agenda", 0), 0.85)

    if not scores:
        if file_type == "image":
            scores["meeting_screenshot"] = 0.4
        else:
            scores["unknown"] = 0.2

    category = max(scores, key=scores.get)
    confidence = min(scores[category], 0.99)

    base = {
        "file_type": file_type,
        "document_category": category if confidence >= 0.35 else "unknown",
        "confidence": round(confidence, 2),
        "needs_manual_confirm": confidence < 0.75,
    }
    return maybe_llm_classify(file_name, ext, sample, base)


def reclassify_vision_from_text(
    *,
    file_name: str,
    ext: str,
    current_category: str | None,
    current_confidence: float | None,
    text: str,
) -> Dict[str, Any] | None:
    """Use OCR text to correct ambiguous image classification after the first vision pass."""
    if not text.strip():
        return None
    candidate = classify_compliance_document(file_name, ext, text)
    candidate_category = candidate.get("document_category")
    candidate_confidence = float(candidate.get("confidence") or 0)
    if not candidate_category or candidate_category == "unknown":
        return None
    if candidate_category == current_category:
        return None
    if candidate_confidence < 0.75:
        return None
    if candidate_confidence <= float(current_confidence or 0):
        return None
    return candidate


def infer_meeting_code(file_names: list[str]) -> str | None:
    for name in file_names:
        m = re.search(r"(?<![A-Z0-9])((?:A1P|SMS)\d+)(?![A-Z0-9])", name, re.I)
        if m:
            return m.group(1).upper()
    return None
