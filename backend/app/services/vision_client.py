from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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

RetryCallback = Callable[[int, int, float, str], None]


def vision_available() -> bool:
    return bool(settings.enable_llm and settings.vision_api_key)


def uses_glm_ocr() -> bool:
    return settings.vision_model.strip().lower().replace("_", "-") == "glm-ocr"


def _vision_chat_url() -> str:
    return settings.vision_base_url.rstrip("/") + "/chat/completions"


def _layout_parsing_url() -> str:
    return settings.vision_base_url.rstrip("/") + "/layout_parsing"


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.vision_api_key}",
        "Content-Type": "application/json",
    }


def _file_data_uri(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".pdf": "application/pdf",
    }.get(suffix, "image/jpeg")
    raw = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{raw}"


def _retry_delay(attempt: int, resp: httpx.Response | None) -> float:
    if resp is not None:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 0.5)
            except ValueError:
                pass
    return settings.vision_retry_base_sec * (2**attempt)


def _post_json_with_retry(
    url: str,
    headers: dict,
    payload: dict,
    *,
    on_retry: Optional[RetryCallback] = None,
) -> dict:
    max_retries = max(settings.vision_retry_max, 0)
    last_rate_msg = "429 Too Many Requests"

    with httpx.Client(timeout=120.0) as client:
        for attempt in range(max_retries + 1):
            try:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code == 429:
                    last_rate_msg = resp.text[:200] or last_rate_msg
                    if attempt >= max_retries:
                        raise FXPGError(
                            f"视觉模型限流（429），已重试 {max_retries} 次: {last_rate_msg}",
                            code="VISION_RATE_LIMITED",
                            status=429,
                        )
                    delay = _retry_delay(attempt, resp)
                    if on_retry:
                        on_retry(attempt + 1, max_retries, delay, last_rate_msg)
                    time.sleep(delay)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict) and data.get("error"):
                    err = data["error"]
                    msg = err.get("message") if isinstance(err, dict) else str(err)
                    raise FXPGError(
                        f"视觉模型返回错误: {msg}",
                        code="VISION_LLM_FAILED",
                        status=502,
                    )
                return data
            except FXPGError:
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    last_rate_msg = exc.response.text[:200] or str(exc)
                    if attempt >= max_retries:
                        raise FXPGError(
                            f"视觉模型限流（429），已重试 {max_retries} 次: {last_rate_msg}",
                            code="VISION_RATE_LIMITED",
                            status=429,
                        ) from exc
                    delay = _retry_delay(attempt, exc.response)
                    if on_retry:
                        on_retry(attempt + 1, max_retries, delay, last_rate_msg)
                    time.sleep(delay)
                    continue
                raise FXPGError(
                    f"视觉模型调用失败: {exc}",
                    code="VISION_LLM_FAILED",
                    status=502,
                ) from exc
            except httpx.HTTPError as exc:
                raise FXPGError(
                    f"视觉模型调用失败: {exc}",
                    code="VISION_LLM_FAILED",
                    status=502,
                ) from exc

    raise FXPGError(
        f"视觉模型限流（429），已重试 {max_retries} 次: {last_rate_msg}",
        code="VISION_RATE_LIMITED",
        status=429,
    )


def _extract_layout_text(data: dict) -> str:
    md = (data.get("md_results") or "").strip()
    if md:
        return md
    parts: List[str] = []
    for page in data.get("layout_details") or []:
        if not isinstance(page, list):
            continue
        for item in page:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if content:
                parts.append(str(content))
    return "\n".join(parts)


def _structure_from_ocr(ocr_text: str, prompt: str) -> Dict[str, Any]:
    from app.services.agent.llm_client import chat_completion, llm_available

    if not llm_available() or not prompt.strip() or not ocr_text.strip():
        return {}
    messages = [
        {
            "role": "system",
            "content": "你是文档信息抽取助手。根据 OCR 文本输出合法 JSON 对象，不要 markdown 代码块。",
        },
        {
            "role": "user",
            "content": f"{prompt}\n\n--- OCR 识别文本 ---\n{ocr_text}",
        },
    ]
    msg = chat_completion(messages, temperature=0.1)
    return _parse_vision_json((msg.get("content") or "").strip())


def _layout_parsing_analyze(
    file_path: Path,
    *,
    prompt: str = "",
    on_retry: Optional[RetryCallback] = None,
) -> Dict[str, Any]:
    payload = {
        "model": "glm-ocr",
        "file": _file_data_uri(file_path),
    }
    data = _post_json_with_retry(
        _layout_parsing_url(),
        _auth_headers(),
        payload,
        on_retry=on_retry,
    )
    ocr_text = _extract_layout_text(data)
    result: Dict[str, Any] = {
        "summary_text": ocr_text,
        "raw_text": ocr_text,
        "md_results": data.get("md_results"),
        "layout_details": data.get("layout_details"),
        "_model": data.get("model") or "glm-ocr",
    }
    if prompt:
        try:
            structured = _structure_from_ocr(ocr_text, prompt)
            if structured:
                result.update(structured)
                if not result.get("summary_text") and structured.get("summary_text"):
                    result["summary_text"] = structured["summary_text"]
        except FXPGError:
            pass
    return result


def _chat_vision_analyze(
    file_path: Path,
    prompt: str,
    max_tokens: int,
    *,
    on_retry: Optional[RetryCallback] = None,
) -> Dict[str, Any]:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": _file_data_uri(file_path)}},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    payload = {
        "model": settings.vision_model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    data = _post_json_with_retry(
        _vision_chat_url(),
        _auth_headers(),
        payload,
        on_retry=on_retry,
    )
    text = data["choices"][0]["message"]["content"].strip()
    parsed = _parse_vision_json(text)
    parsed["_model"] = settings.vision_model
    return parsed


def vision_analyze_image(
    file_path: Path,
    prompt: str = INVOICE_VISION_PROMPT,
    max_tokens: int = 2048,
    *,
    on_retry: Optional[RetryCallback] = None,
) -> Dict[str, Any]:
    """调用 GLM-OCR（layout_parsing）或 GLM-V 多模态（chat/completions）理解图片。"""
    if not vision_available():
        raise FXPGError("未配置视觉模型 VISION_API_KEY", code="VISION_NOT_CONFIGURED", status=503)

    if uses_glm_ocr():
        return _layout_parsing_analyze(file_path, prompt=prompt, on_retry=on_retry)
    return _chat_vision_analyze(file_path, prompt, max_tokens, on_retry=on_retry)


def vision_analyze_pil_image(
    img,
    prompt: str = INVOICE_VISION_PROMPT,
    *,
    on_retry: Optional[RetryCallback] = None,
) -> Dict[str, Any]:
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
        return vision_analyze_image(tmp_path, prompt=prompt, on_retry=on_retry)
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
    if not parts and data.get("md_results"):
        parts.append(str(data["md_results"]))
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
