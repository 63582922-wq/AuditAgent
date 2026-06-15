from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import settings
from app.exceptions import FXPGError


def safe_relative_path(name: str) -> Path:
    """防止路径穿越，保留文件夹内相对路径。"""
    normalized = name.replace("\\", "/").strip()
    if not normalized or normalized.startswith("/"):
        raise FXPGError("无效的文件路径", code="INVALID_PATH", status=400)
    parts = [p for p in normalized.split("/") if p and p not in (".", "..")]
    if not parts:
        raise FXPGError("无效的文件路径", code="INVALID_PATH", status=400)
    return Path(*parts)


def staging_root() -> Path:
    root = settings.storage_path / "case_staging"
    root.mkdir(parents=True, exist_ok=True)
    return root


async def stage_case_upload(files: list[UploadFile]) -> Path:
    """将浏览器上传的案件文件夹写入临时目录，供 import_case_folder 使用。"""
    if not files:
        raise FXPGError("请选择包含资料的文件夹", code="NO_FILES", status=400)

    case_dir = staging_root() / uuid.uuid4().hex
    case_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    saved = 0

    try:
        for uf in files:
            if not uf.filename:
                continue
            rel = safe_relative_path(uf.filename)
            ext = rel.suffix.lower()
            if ext and ext not in settings.allowed_extensions:
                continue

            dest = case_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)

            size = 0
            with dest.open("wb") as f:
                while chunk := await uf.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise FXPGError(
                            f"文件 {rel.name} 超过 {settings.max_upload_mb}MB 限制",
                            code="FILE_TOO_LARGE",
                            status=400,
                        )
                    f.write(chunk)
            saved += 1

        if saved == 0:
            raise FXPGError("文件夹内没有支持的资料格式", code="NO_VALID_FILES", status=400)
        return case_dir
    except Exception:
        cleanup_staged_case(case_dir)
        raise


def cleanup_staged_case(case_dir: Path) -> None:
    shutil.rmtree(case_dir, ignore_errors=True)
