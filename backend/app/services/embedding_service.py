from __future__ import annotations

import hashlib
import math
import re
from typing import List, Optional

import httpx

from app.config import settings

_EMBED_DIM = 384


def embedding_dim() -> int:
    return _EMBED_DIM


def embed_text(text: str) -> List[float]:
    """生成文本向量。OpenAI 兼容 embeddings 可用时用 API，否则本地哈希向量。"""
    text = (text or "").strip()
    if not text:
        return [0.0] * _EMBED_DIM
    if settings.text_api_key and _remote_embedding_supported():
        try:
            return _openai_embed(text)
        except Exception:
            pass
    return _local_embed(text)


def _remote_embedding_supported() -> bool:
    """DeepSeek 等 chat 端点不提供 /embeddings，启动时直接走本地向量。"""
    base = settings.text_base_url.lower()
    if "deepseek.com" in base:
        return False
    return True


def _openai_embed(text: str) -> List[float]:
    base = settings.text_base_url.rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1"
    url = base + "/embeddings"
    headers = {"Authorization": f"Bearer {settings.text_api_key}"}
    payload = {"model": "text-embedding-3-small", "input": text[:8000], "dimensions": _EMBED_DIM}
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()["data"][0]["embedding"]
        return [float(x) for x in data]


def _local_embed(text: str) -> List[float]:
    """字符 n-gram 哈希向量，无需外部依赖。"""
    vec = [0.0] * _EMBED_DIM
    tokens = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", text.lower())
    if not tokens:
        tokens = [text[:32]]
    for token in tokens:
        for n in (2, 3):
            for i in range(max(len(token) - n + 1, 1)):
                gram = token[i : i + n] if len(token) >= n else token
                h = int(hashlib.md5(gram.encode()).hexdigest(), 16)
                idx = h % _EMBED_DIM
                sign = 1.0 if (h >> 8) & 1 else -1.0
                vec[idx] += sign
    return _normalize(vec)


def _normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


def cosine_similarity(a: Optional[List[float]], b: Optional[List[float]]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def embed_memory_content(content: str, tags: Optional[List[str]] = None) -> List[float]:
    tag_part = " ".join(tags or [])
    return embed_text(f"{content}\n{tag_part}".strip())
