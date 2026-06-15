from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.exceptions import FXPGError

AGENT_REQUIRED_MSG = (
    "本系统为纯智能体模式，必须配置文本 LLM。"
    "请在 backend/.env 设置 LLM_API_KEY（DeepSeek）与 ENABLE_LLM=true。"
)

LLM_RETRY_MAX = 3
LLM_RETRY_BASE_SEC = 1.0

_DOMAIN_SYSTEM_PROMPTS = {
    "accounting": "你是会计风险评估 Agent 的推理模块。只输出合法 JSON 对象，不要 markdown 代码块。",
    "compliance": (
        "你是会议合规观察（remote observation）Agent 的推理模块。"
        "只输出合法 JSON 对象，不要 markdown 代码块。"
    ),
}


def llm_available() -> bool:
    return bool(settings.enable_llm and settings.text_api_key)


def require_agent_llm() -> None:
    if not settings.enable_llm:
        raise FXPGError("ENABLE_LLM 未启用，智能体无法运行", code="AGENT_DISABLED", status=503)
    if not settings.text_api_key:
        raise FXPGError(AGENT_REQUIRED_MSG, code="AGENT_LLM_REQUIRED", status=503)


def _is_retryable_status(status_code: int) -> bool:
    return status_code >= 500 or status_code in (408, 429)


def chat_completion(
    messages: List[Dict[str, str]],
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,
    temperature: float = 0.2,
) -> Dict[str, Any]:
    require_agent_llm()
    base = settings.text_base_url.rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1"
    url = base + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.text_api_key}", "Content-Type": "application/json"}
    payload: Dict[str, Any] = {
        "model": settings.text_model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice or "auto"

    last_exc: Optional[Exception] = None
    for attempt in range(1, LLM_RETRY_MAX + 1):
        try:
            with httpx.Client(timeout=90.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code >= 400 and _is_retryable_status(resp.status_code) and attempt < LLM_RETRY_MAX:
                    last_exc = httpx.HTTPStatusError(
                        f"server error {resp.status_code}", request=resp.request, response=resp
                    )
                    time.sleep(LLM_RETRY_BASE_SEC * (2 ** (attempt - 1)))
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            if attempt >= LLM_RETRY_MAX:
                break
            time.sleep(LLM_RETRY_BASE_SEC * (2 ** (attempt - 1)))
            continue
        except httpx.HTTPError as exc:
            raise FXPGError(f"文本 LLM 调用失败: {exc}", code="AGENT_LLM_FAILED", status=502) from exc

    raise FXPGError(
        f"文本 LLM 调用失败（已重试 {LLM_RETRY_MAX} 次）: {last_exc}",
        code="AGENT_LLM_FAILED",
        status=502,
    ) from last_exc


def chat_json(
    messages: List[Dict[str, str]],
    schema_hint: str = "",
    domain: Optional[str] = None,
) -> Dict[str, Any]:
    require_agent_llm()
    active_domain = (domain or settings.agent_domain or "accounting").lower()
    base_prompt = _DOMAIN_SYSTEM_PROMPTS.get(active_domain, _DOMAIN_SYSTEM_PROMPTS["accounting"])
    sys = base_prompt + (f" 格式要求：{schema_hint}" if schema_hint else "")
    msgs = [{"role": "system", "content": sys}] + messages
    msg = chat_completion(msgs, temperature=0.1)
    text = (msg.get("content") or "").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("expected object")
        return data
    except (json.JSONDecodeError, ValueError) as exc:
        raise FXPGError(f"LLM 返回非 JSON: {text[:200]}", code="AGENT_LLM_INVALID", status=502) from exc
