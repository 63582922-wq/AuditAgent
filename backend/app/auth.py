from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from app.config import settings


def require_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> None:
    if not settings.api_key:
        if settings.app_env.lower() == "production":
            raise HTTPException(status_code=401, detail="服务未配置 API Key")
        return
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="无效的 API Key")
