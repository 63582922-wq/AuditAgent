from __future__ import annotations

import json
import re
import shutil
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import openpyxl
from sqlalchemy.orm import Session

from app.config import settings
from app.models import FileRecord, Meeting, Project
from app.services.domain.compliance.classifier import classify_compliance_document, infer_meeting_code
from app.services.meeting_service import create_meeting


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _parse_metadata_excel(path: Path) -> Dict[str, Any]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=1, max_row=5, values_only=True))
    wb.close()
    if len(rows) < 2:
        return {}
    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    values = rows[1]
    profile = {}
    for h, v in zip(headers, values):
        if h and v is not None:
            profile[h] = v
    mapping = {
        "观察类型": "observation_type",
        "本场会议是否成功观察": "observation_success",
        "会议组织者配合程度": "organizer_cooperation",
        "是否是Surprise Check\n联系组织者为“否”\n不联系组织者为“是”": "surprise_check",
        "会议类型": "meeting_type",
        "会议编码": "meeting_code",
        "总预算金额": "total_budget",
        "BU": "bu",
        "申请人姓名": "applicant",
    }
    normalized: Dict[str, Any] = {}
    for k, v in profile.items():
        key = mapping.get(k, k)
        normalized[key] = _json_safe(v)
    return normalized


def _extract_meeting_from_pdf_text(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    patterns = {
        "meeting_code": r"会议编号[：:]\s*(A1P\d+)",
        "meeting_title": r"(宝山[^\n]{0,30})",
        "meeting_date": r"会议日期[：:]\s*(\d{4}-\d{2}-\d{2})",
        "speaker_name": r"讲者/主\s*席姓名\s*(\S+)",
        "speaker_duration": r"演讲时长\s*分钟\s*(\d+)",
        "material_code": r"(Promotional[^\s]+|M-CN-\d+)",
        "total_budget": r"计划会议预算（含讲课费）[：:]\s*[￥¥]?([\d,\.]+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, re.I)
        if m:
            out[key] = m.group(1).strip()
    return out


def import_case_folder(
    db: Session,
    case_path: Path,
    project_name: Optional[str] = None,
    *,
    project_id: Optional[str] = None,
    meeting_id: Optional[str] = None,
) -> tuple[str, str, Dict[str, Any]]:
    """将 FX 案件文件夹导入为项目+子会议，或向已有子会议追加资料。返回 (project_id, meeting_id, profile)。"""
    case_path = case_path.resolve()
    if not case_path.is_dir():
        raise ValueError(f"案件目录不存在: {case_path}")

    all_files = [p for p in case_path.rglob("*") if p.is_file() and not p.name.startswith(".")]
    if not all_files:
        raise ValueError("案件目录为空")

    meeting_code = infer_meeting_code([p.name for p in all_files]) or "UNKNOWN"
    meeting_profile: Dict[str, Any] = {"meeting_code": meeting_code, "source_folder": str(case_path)}

    if project_id and meeting_id:
        project = db.get(Project, project_id)
        meeting = db.get(Meeting, meeting_id)
        if not project or not meeting or meeting.project_id != project_id:
            raise ValueError("项目或子会议不存在")
    elif project_id:
        project = db.get(Project, project_id)
        if not project:
            raise ValueError("项目不存在")
        meeting = create_meeting(
            db,
            project_id,
            meeting_code=meeting_code,
            meeting_title=project_name or f"会议 {meeting_code}",
        )
        meeting_id = meeting.id
    else:
        name = project_name or f"观察项目 {meeting_code}"
        project = Project(name=name, status="active")
        db.add(project)
        db.commit()
        db.refresh(project)
        meeting = create_meeting(
            db,
            project.id,
            meeting_code=meeting_code,
            meeting_title=f"会议 {meeting_code}",
        )
        project_id = project.id
        meeting_id = meeting.id

    upload_dir = settings.storage_path / "uploads" / project_id / meeting_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved: List[Dict[str, Any]] = []

    for src in all_files:
        ext = src.suffix.lower()
        if ext not in settings.allowed_extensions:
            continue

        text_preview = ""
        if ext == ".pdf":
            try:
                from app.services.parsers.pdf_parser import parse_pdf

                text_preview = (parse_pdf(src).get("text_content") or "")[:12000]
            except Exception:
                pass
        elif ext == ".xlsx":
            if "finding" not in src.name.lower() and "roche" not in src.name.lower():
                try:
                    meeting_profile.update(_parse_metadata_excel(src))
                except Exception:
                    pass

        classification = classify_compliance_document(src.name, ext, text_preview)
        dest = upload_dir / src.name
        if dest.exists():
            dest = upload_dir / f"{src.stem}_{len(saved)}{ext}"
        shutil.copy2(src, dest)

        fr = FileRecord(
            project_id=project_id,
            meeting_id=meeting_id,
            file_name=src.name,
            file_type=classification["file_type"],
            document_category=classification["document_category"],
            storage_path=str(dest),
            confidence=classification["confidence"],
            meta_json=classification,
        )
        db.add(fr)
        saved.append({"file_name": src.name, "category": classification["document_category"]})

    db.commit()

    for src in all_files:
        if src.suffix.lower() == ".pdf":
            try:
                from app.services.parsers.pdf_parser import parse_pdf

                text = parse_pdf(src).get("text_content") or ""
                meeting_profile.update(_extract_meeting_from_pdf_text(text))
            except Exception:
                pass

    meeting = db.get(Meeting, meeting_id)
    if meeting:
        state = dict(meeting.state_json or {})
        state["meeting_case"] = _json_safe(meeting_profile)
        state["imported_files"] = saved
        state["agent_domain"] = "compliance"
        meeting.state_json = state
        meeting.observation_type = meeting_profile.get("observation_type") or meeting.observation_type
        meeting.meeting_type = meeting_profile.get("meeting_type") or meeting.meeting_type
        meeting.status = "ready"
        meeting.updated_at = datetime.now(timezone.utc)
        db.commit()

    project = db.get(Project, project_id)
    if project:
        project.status = "active"
        db.commit()

    return project_id, meeting_id, meeting_profile


def bootstrap_meeting_profile(db: Session, project_id: str, meeting_id: Optional[str] = None) -> Dict[str, Any]:
    """从已上传文件推断 meeting_case。"""
    q = db.query(FileRecord).filter_by(project_id=project_id)
    if meeting_id:
        q = q.filter_by(meeting_id=meeting_id)
    files = q.all()
    if not files:
        return {}

    meeting_code = infer_meeting_code([f.file_name for f in files]) or "UNKNOWN"
    profile: Dict[str, Any] = {"meeting_code": meeting_code}

    for f in files:
        path = Path(f.storage_path)
        if path.suffix.lower() != ".xlsx":
            continue
        if "finding" in f.file_name.lower() or "roche" in f.file_name.lower():
            continue
        try:
            profile.update(_parse_metadata_excel(path))
        except Exception:
            pass

    for f in files:
        if Path(f.file_name).suffix.lower() != ".pdf":
            continue
        try:
            from app.services.parsers.pdf_parser import parse_pdf

            text = parse_pdf(Path(f.storage_path)).get("text_content") or ""
            profile.update(_extract_meeting_from_pdf_text(text))
        except Exception:
            pass

    return _json_safe(profile)
