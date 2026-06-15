from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

from app.services.domain.compliance.constants import CATEGORY_KEYWORDS
from app.services.domain.compliance.llm_classify import maybe_llm_classify


def classify_compliance_document(file_name: str, ext: str, text: str = "") -> Dict[str, Any]:
    lower = file_name.lower()
    scores: Dict[str, float] = {}

    for category, keywords in CATEGORY_KEYWORDS.items():
        hit = sum(1 for kw in keywords if kw.lower() in lower)
        if hit:
            scores[category] = min(0.5 + hit * 0.2, 0.98)

    if re.search(r"a1p\d+", lower):
        scores["a1_meeting_export"] = max(scores.get("a1_meeting_export", 0), 0.95)
    if "supporting" in lower:
        scores["observation_confirmation"] = scores.get("observation_confirmation", 0) + 0.1

    sample = (text or "")[:8000]
    if sample:
        if "会议编号" in sample or "A1 Platform" in sample:
            scores["a1_meeting_export"] = max(scores.get("a1_meeting_export", 0), 0.9)
        if "观察记录确认书" in sample or "现场确认" in sample:
            scores["observation_confirmation"] = max(scores.get("observation_confirmation", 0), 0.9)
        if "签到列表" in sample or "签到时间" in sample:
            scores["sign_in_record"] = max(scores.get("sign_in_record", 0), 0.85)
        if "会议日程" in sample and "环节类型" in sample:
            scores["meeting_agenda"] = max(scores.get("meeting_agenda", 0), 0.85)

    ext_map = {
        ".xlsx": "excel", ".xls": "excel", ".csv": "excel",
        ".docx": "word", ".doc": "word",
        ".pdf": "pdf", ".jpg": "image", ".jpeg": "image", ".png": "image",
    }
    file_type = ext_map.get(ext.lower(), "unknown")

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


def infer_meeting_code(file_names: list[str]) -> str | None:
    for name in file_names:
        m = re.search(r"(A1P\d+)", name, re.I)
        if m:
            return m.group(1).upper()
    return None
