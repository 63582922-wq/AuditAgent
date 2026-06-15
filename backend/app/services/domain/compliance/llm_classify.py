from __future__ import annotations

from typing import Any, Dict

from app.services.agent.llm_client import chat_json, llm_available
from app.services.domain.compliance.constants import CATEGORY_KEYWORDS, DOCUMENT_CATEGORY_LABELS

VALID_CATEGORIES = list(CATEGORY_KEYWORDS.keys())


def maybe_llm_classify(
    file_name: str,
    ext: str,
    text: str,
    base: Dict[str, Any],
) -> Dict[str, Any]:
    """低置信度或 unknown 时，用 LLM 辅助资料分类。"""
    if base.get("document_category") not in ("unknown", None) and not base.get("needs_manual_confirm"):
        return base
    if not llm_available():
        return base

    labels = {k: DOCUMENT_CATEGORY_LABELS.get(k, k) for k in VALID_CATEGORIES}
    preview = (text or "")[:3500]
    prompt = (
        "你是会议合规远程观察资料分拣助手。根据文件名与内容预览，判断资料类型。\n"
        f"文件名：{file_name}\n扩展名：{ext}\n"
        f"可选类别（document_category）：{labels}\n"
        f"内容预览：\n{preview or '（无文本预览）'}\n"
        '输出 JSON：{"document_category":"类别key","confidence":0.0-1.0,"reason":"一句话"}'
    )
    try:
        result = chat_json(
            [{"role": "user", "content": prompt}],
            schema_hint='{"document_category":"","confidence":0.0,"reason":""}',
            temperature=0.1,
        )
        cat = str(result.get("document_category") or "")
        conf = float(result.get("confidence") or 0)
        if cat in VALID_CATEGORIES and conf >= 0.45:
            merged = dict(base)
            merged["document_category"] = cat if conf >= 0.35 else "unknown"
            merged["confidence"] = round(min(conf, 0.99), 2)
            merged["needs_manual_confirm"] = conf < 0.75
            merged["llm_classified"] = True
            if result.get("reason"):
                merged["llm_reason"] = str(result["reason"])[:200]
            return merged
    except Exception:
        pass
    return base
