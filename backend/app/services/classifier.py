from __future__ import annotations

import re
from pathlib import Path

from app.config import settings
from app.services.constants import CATEGORY_KEYWORDS, FIELD_ALIASES, HEADER_KEYWORDS


def classify_by_extension(ext: str) -> dict[str, float]:
    ext = ext.lower()
    mapping = {
        ".xlsx": "excel",
        ".xls": "excel",
        ".csv": "excel",
        ".docx": "word",
        ".doc": "word",
        ".pdf": "pdf",
        ".jpg": "image",
        ".jpeg": "image",
        ".png": "image",
    }
    file_type = mapping.get(ext, "unknown")
    return {file_type: 1.0}


def classify_by_filename(name: str) -> dict[str, float]:
    scores: dict[str, float] = {}
    lower = name.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        hit = sum(1 for kw in keywords if kw in lower)
        if hit:
            scores[category] = min(0.4 + hit * 0.15, 0.95)
    return scores


def classify_by_headers(headers: list[str]) -> dict[str, float]:
    if not headers:
        return {}
    joined = " ".join(headers)
    scores: dict[str, float] = {}
    if any(k in joined for k in ["借方", "贷方", "科目编码", "科目名称"]):
        scores["trial_balance"] = 0.85
    if any(k in joined for k in ["发票号码", "价税合计", "税额", "发票代码"]):
        scores["invoice_list"] = 0.9
    if any(k in joined for k in ["对方户名", "银行账号", "交易时间", "借方发生", "贷方发生"]):
        scores["bank_statement"] = 0.9
    if any(k in joined for k in ["摘要", "金额"]) and "发票" not in joined:
        scores["expense_detail"] = 0.75
    return scores


def classify_document(
    file_name: str,
    ext: str,
    headers: list[str] | None = None,
    text: str = "",
    *,
    domain: str | None = None,
) -> dict:
    domain = (domain or settings.agent_domain or "compliance").lower()
    if domain == "compliance":
        from app.services.domain.compliance.classifier import classify_compliance_document

        return classify_compliance_document(file_name, ext, text)

    scores: dict[str, float] = {"unknown": 0.1}
    for part in (
        classify_by_filename(file_name),
        classify_by_headers(headers or []),
    ):
        for k, v in part.items():
            scores[k] = scores.get(k, 0) + v

    if text:
        for category, keywords in CATEGORY_KEYWORDS.items():
            hit = sum(1 for kw in keywords if kw in text[:5000])
            if hit:
                scores[category] = scores.get(category, 0) + min(hit * 0.1, 0.5)

    category = max(scores, key=scores.get)
    confidence = min(scores[category], 0.99)
    ext_scores = classify_by_extension(ext)
    file_type = max(ext_scores, key=ext_scores.get)

    return {
        "file_type": file_type,
        "document_category": category if confidence >= 0.35 else "unknown",
        "confidence": round(confidence, 2),
        "needs_manual_confirm": confidence < 0.75,
    }


def detect_header_row(rows: list[list]) -> int:
    candidates: list[tuple[int, float]] = []
    scan = rows[:20]
    for idx, row in enumerate(scan):
        cells = [str(c).strip() if c is not None else "" for c in row]
        non_empty = sum(1 for c in cells if c)
        keyword_score = sum(
            1 for c in cells for kw in HEADER_KEYWORDS if kw in c
        )
        next_score = 0.0
        if idx + 1 < len(scan):
            next_cells = [str(c).strip() if c is not None else "" for c in scan[idx + 1]]
            next_score = 1.0 if any(re.search(r"\d", c) for c in next_cells) else 0.2
        total = non_empty * 0.2 + keyword_score * 0.6 + next_score * 0.2
        candidates.append((idx, total))
    if not candidates:
        return 0
    return max(candidates, key=lambda x: x[1])[0]


def normalize_field(column_name: str) -> tuple[str | None, float]:
    col = column_name.strip()
    for standard, aliases in FIELD_ALIASES.items():
        if col in aliases or any(a in col for a in aliases):
            return standard, 0.96
    return None, 0.0


def clean_entity_name(name: str) -> str:
    name = name.strip()
    for suffix in ["有限公司", "有限责任公司", "股份有限公司", "公司"]:
        name = name.replace(suffix, "")
    name = re.sub(r"\s+", "", name)
    name = name.replace("（", "(").replace("）", ")")
    return name
