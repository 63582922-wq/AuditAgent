from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Tuple

from app.models import FileRecord

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
VISION_AGENT_ID = "vision_agent"
TEXT_INGEST_AGENT_ID = "text_ingest"


def is_vision_file(file: FileRecord) -> bool:
    if (file.file_type or "").lower() == "image":
        return True
    return Path(file.file_name).suffix.lower() in IMAGE_SUFFIXES


def split_files_by_modality(files: Iterable[FileRecord]) -> Tuple[List[FileRecord], List[FileRecord]]:
    text_files: List[FileRecord] = []
    vision_files: List[FileRecord] = []
    for f in files:
        if is_vision_file(f):
            vision_files.append(f)
        else:
            text_files.append(f)
    return text_files, vision_files


def agent_modality(agent_id: str, cfg: dict) -> str:
    if agent_id == VISION_AGENT_ID:
        return "vision"
    declared = cfg.get("modality")
    if declared in ("vision", "text", "mixed"):
        return declared
    doc_types = set(cfg.get("doc_types") or [])
    image_cats = {
        "meeting_screenshot",
        "observation_confirmation",
        "sign_in_record",
        "coordination_sms",
        "presentation_material",
        "speaker_profile",
        "invoice_image",
    }
    if doc_types and doc_types <= image_cats:
        return "vision"
    if doc_types & image_cats:
        return "mixed"
    return "text"
