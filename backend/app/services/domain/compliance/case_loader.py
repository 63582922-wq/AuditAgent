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


CASE_FOLDER_RE = re.compile(r"Remote_(?:A1P|SMS)\d+_\d{8}_.+_Supporting$", re.I)
CASE_CODE_RE = re.compile(r"(?<![A-Z0-9])((?:A1P|SMS)\d+)(?![A-Z0-9])", re.I)
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


def _case_codes_from_paths(case_path: Path, all_files: list[Path]) -> set[str]:
    codes: set[str] = set()
    for path in all_files:
        try:
            rel_text = str(path.relative_to(case_path))
        except ValueError:
            rel_text = path.name
        for match in CASE_CODE_RE.finditer(rel_text):
            codes.add(match.group(1).upper())
    return codes


def _supporting_roots(case_path: Path, all_files: list[Path]) -> set[Path]:
    roots: set[Path] = set()
    for path in all_files:
        try:
            rel = path.relative_to(case_path)
        except ValueError:
            continue
        for idx, part in enumerate(rel.parts[:-1]):
            if CASE_FOLDER_RE.match(part):
                roots.add(case_path.joinpath(*rel.parts[: idx + 1]))
                break
    return roots


def _resolve_logical_case_path(case_path: Path, all_files: list[Path]) -> Path:
    supporting_roots = _supporting_roots(case_path, all_files)
    if len(supporting_roots) > 1:
        examples = "、".join(sorted(root.name for root in supporting_roots)[:3])
        raise ValueError(f"请选择单场观察案件文件夹；当前目录包含多个 Supporting 案件：{examples}")
    codes = _case_codes_from_paths(case_path, all_files)
    if len(codes) > 1:
        raise ValueError(f"请选择单场观察案件文件夹；当前目录包含多个会议编码：{', '.join(sorted(codes))}")
    if len(supporting_roots) == 1:
        return next(iter(supporting_roots))
    return case_path


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
        "meeting_type": r"会议类型[：:]\s*([^\n\r]+)",
        "applicant": r"会议申请人[：:]\s*([^（\n\r]+)",
        "planned_organizer_name": r"会议组织者[：:]\s*([^（\n\r]+)",
        "organizer_department": r"组织者部门[：:]\s*([^\n\r]+)",
        "city": r"会议城市[：:]\s*([^\n\r]+)",
        "product_name": r"产品[：:]\s*([^\n\r]+)",
        "meeting_location_type": r"院内/院外[：:]\s*([^\n\r]+)",
        "line_manager_name": r"直\s*线\s*经\s*理[：:]\s*([^（\n\r]+)",
        "line_manager_email": r"直\s*线\s*经\s*理[：:][^\n\r]*?([A-Za-z0-9._%+-]+@roche\.com)",
        "speaker_service_minutes": r"演讲时长\s*分钟\s*(\d+)",
        "material_code": r"(Promotional[^\s]+|M-CN-\d+)",
        "total_budget": r"计划会议预算（含讲课费）[：:]\s*[￥¥]?([\d,\.]+)",
        "planned_speaker_budget": r"讲课费预算小计[：:]\s*[￥¥]?([\d,\.]+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, re.I)
        if m:
            out[key] = m.group(1).strip()
    attendees = re.search(
        r"会议人数[：:]?\s*总人数[：:]?\s*(\d+).*?内部人数[：:]?\s*(\d+).*?外部人数[：:]?\s*(\d+)",
        text,
        re.S,
    )
    if attendees:
        out["planned_roche_staff"] = int(attendees.group(2))
        out["planned_attendees"] = int(attendees.group(3))
    agenda = re.search(
        r"(20\d{2}-\d{1,2}-\d{1,2})\s+(\d{1,2}:\d{2})\s*[-~至]\s*(\d{1,2}:\d{2})",
        re.sub(r"\s+", " ", text),
    )
    if agenda:
        out["meeting_date"] = agenda.group(1)
        out["planned_start_time"] = agenda.group(2)
        out["planned_end_time"] = agenda.group(3)
    speaker = re.search(r"\n([\u4e00-\u9fff]{2,4})\n临床医生\n(?:国家级|省级|市级)", text)
    if speaker:
        out["speaker_name"] = speaker.group(1)
    return out


def _extract_pdf_text_preview(path: Path, max_chars: int = 12000) -> str:
    """Read embedded PDF text for import-time metadata only.

    Full OCR, image-page analysis, and table extraction belong to the later
    ingest/vision workflow. Import must stay cheap and must not decide whether
    scanned pages contain evidence.
    """
    try:
        import fitz

        chunks: list[str] = []
        with fitz.open(path) as doc:
            for page in doc:
                text = page.get_text("text") or ""
                if text:
                    chunks.append(text)
                if sum(len(chunk) for chunk in chunks) >= max_chars:
                    break
        return "\n".join(chunks)[:max_chars]
    except Exception:
        return ""


def _infer_profile_from_names(case_path: Path, file_names: list[str]) -> Dict[str, Any]:
    text = " ".join([case_path.name, *file_names])
    profile: Dict[str, Any] = {}
    if re.search(r"(^|[_\-\s])remote([_\-\s]|$)", text, re.I) or "远程" in text:
        profile["observation_type"] = "远程观察"
    elif re.search(r"(^|[_\-\s])(onsite|现场)([_\-\s]|$)", text, re.I):
        profile["observation_type"] = "现场观察"

    date_match = re.search(r"(?:A1P|SMS)\d+[_\-\s]+(20\d{6})", text, re.I) or re.search(r"(20\d{6})", text)
    if date_match:
        raw = date_match.group(1)
        date_value = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        profile["meeting_date"] = date_value
        profile["会议计划日期"] = date_value
        profile["实际会议日期"] = date_value
    return profile


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

    logical_case_path = _resolve_logical_case_path(case_path, all_files)
    file_names = [p.name for p in all_files]
    meeting_code = infer_meeting_code(file_names) or "UNKNOWN"
    meeting_profile: Dict[str, Any] = {
        "meeting_code": meeting_code,
        "source_folder": str(logical_case_path),
        **_infer_profile_from_names(logical_case_path, file_names),
    }

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
    pdf_text_cache: Dict[Path, str] = {}

    for src in all_files:
        ext = src.suffix.lower()
        if ext not in settings.allowed_extensions:
            continue

        text_preview = ""
        if ext == ".pdf":
            text_preview = _extract_pdf_text_preview(src)
            pdf_text_cache[src] = text_preview
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
            text = pdf_text_cache.get(src)
            if text is None:
                text = _extract_pdf_text_preview(src)
            if text:
                meeting_profile.update(_extract_meeting_from_pdf_text(text))

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

    file_names = [f.file_name for f in files]
    meeting_code = infer_meeting_code(file_names) or "UNKNOWN"
    source_folder = ""
    for f in files:
        try:
            source_folder = str(Path(f.storage_path).parents[1])
            break
        except IndexError:
            pass
    profile: Dict[str, Any] = {
        "meeting_code": meeting_code,
        **_infer_profile_from_names(Path(source_folder or "."), file_names),
    }

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
