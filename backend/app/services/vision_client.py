from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.exceptions import FXPGError

INVOICE_VISION_PROMPT = """你是会计票据识别专家。请阅读这张发票/财务图片，提取关键字段。
只输出 JSON 对象，不要 markdown，字段名用英文：
{
  "invoice_number": "",
  "invoice_date": "",
  "buyer_name": "",
  "seller_name": "",
  "total_amount": 0,
  "tax_amount": 0,
  "tax_rate": "",
  "summary_text": "图片全文摘要"
}
无法识别的字段留空或 0。"""


def vision_available() -> bool:
    return bool(settings.enable_llm and settings.vision_api_key)


def _vision_url() -> str:
    return settings.vision_base_url.rstrip("/") + "/chat/completions"


def _image_data_url(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "image/jpeg")
    raw = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{raw}"


def vision_analyze_image(
    file_path: Path,
    prompt: str = INVOICE_VISION_PROMPT,
    max_tokens: int = 2048,
) -> Dict[str, Any]:
    """调用 GLM-4.6V 等视觉模型理解图片。"""
    if not vision_available():
        raise FXPGError("未配置视觉模型 VISION_API_KEY", code="VISION_NOT_CONFIGURED", status=503)

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": _image_data_url(file_path)}},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    headers = {
        "Authorization": f"Bearer {settings.vision_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.vision_model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(_vision_url(), headers=headers, json=payload)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
    except httpx.HTTPError as exc:
        raise FXPGError(f"视觉模型调用失败: {exc}", code="VISION_LLM_FAILED", status=502) from exc

    return _parse_vision_json(text)


def vision_analyze_pil_image(img, prompt: str = INVOICE_VISION_PROMPT) -> Dict[str, Any]:
    """PDF 页面转 PIL 后调用视觉模型。"""
    import io
    import tempfile

    if not vision_available():
        raise FXPGError("未配置视觉模型", code="VISION_NOT_CONFIGURED", status=503)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(buf.getvalue())
        tmp_path = Path(tmp.name)
    try:
        return vision_analyze_image(tmp_path, prompt=prompt)
    finally:
        tmp_path.unlink(missing_ok=True)


def _parse_vision_json(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {"summary_text": text, "raw_text": text}


def vision_fields_to_text(data: Dict[str, Any]) -> str:
    parts: List[str] = []
    if data.get("summary_text"):
        parts.append(str(data["summary_text"]))
    if data.get("raw_text") and not data.get("summary_text"):
        parts.append(str(data["raw_text"]))
    for key, label in [
        ("invoice_number", "发票号码"),
        ("invoice_date", "开票日期"),
        ("buyer_name", "购买方"),
        ("seller_name", "销售方"),
        ("total_amount", "价税合计"),
        ("tax_amount", "税额"),
        ("tax_rate", "税率"),
    ]:
        val = data.get(key)
        if val not in (None, "", 0):
            parts.append(f"{label}: {val}")
    return "\n".join(parts)


def normalize_vision_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    mapping = {
        "invoice_number": "invoice_number",
        "invoice_date": "invoice_date",
        "buyer_name": "buyer_name",
        "seller_name": "seller_name",
        "total_amount": "total_amount",
        "tax_amount": "tax_amount",
        "tax_rate": "tax_rate",
    }
    for src, dst in mapping.items():
        val = data.get(src)
        if val in (None, ""):
            continue
        if dst in ("total_amount", "tax_amount"):
            try:
                val = float(str(val).replace(",", ""))
            except (TypeError, ValueError):
                continue
        fields[dst] = val
    return fields
