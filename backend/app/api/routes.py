from __future__ import annotations

import shutil
from pathlib import Path

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.config import settings
from app.database import get_db
from app.exceptions import FXPGError
from app.models import (
    AgentRunLog,
    AnalysisJob,
    ExtractedEntity,
    FileRecord,
    Meeting,
    Memory,
    Output,
    ParsedDocument,
    Project,
    RecordLink,
    ReviewRecord,
    Risk,
    Rule,
)
from app.schemas import (
    AnalyzeResponse,
    AgentActionApproveRequest,
    AgentActionApproveResponse,
    AgentChatRequest,
    AgentChatResponse,
    FileOut,
    JobOut,
    MeetingBatchDelete,
    MeetingCreate,
    MeetingOut,
    MeetingUpdate,
    MemoryCreate,
    MemoryOut,
    ProjectBatchDelete,
    ProjectCreate,
    ProjectDetail,
    ProjectLiveOut,
    ProjectOut,
    ProjectOverviewOut,
    ProjectSummary,
    ProjectUpdate,
    ReviewCreate,
    DeliverableReview,
    ReanalyzeRequest,
    RiskOut,
    RuleCreate,
    RuleOut,
    StatsOut,
    HarnessImportRequest,
    HarnessRunRequest,
    HarnessResultOut,
)
from app.services.meeting_service import (
    accept_meeting_deliverables,
    create_meeting,
    delete_meetings_batch,
    delete_meeting_cascade,
    ensure_default_meeting,
    get_meeting,
    list_meetings,
    meeting_to_dict,
    reject_meeting_deliverables,
    sync_project_rollups,
    update_meeting,
)
from app.services.agent.workflow import AgentWorkflow
from app.services.harness_job_service import start_harness_job
from app.services.agent.memory_writer import write_review_memory
from app.services.agent.llm_client import llm_available, require_agent_llm
from app.services.agent.action_executor import approve_agent_action
from app.services.agent.main_chat import run_main_agent_chat
from app.services.domain.registry import get_domain_pack, resolve_agent_domain
from app.services.jobs.worker import create_job, enqueue_analysis, enqueue_harness
from app.services.project_live_service import (
    build_meeting_live,
    build_project_live,
    latest_meeting_job as load_latest_meeting_job,
    latest_project_job as load_latest_project_job,
    list_meeting_logs as load_meeting_logs,
    list_project_logs as load_project_logs,
)
from app.services.output_scope import primary_output_count, primary_outputs
from app.services.seed import seed_memories, seed_rules

router = APIRouter(dependencies=[Depends(require_api_key)])


def _is_compliance_project(project: Project) -> bool:
    state = project.state_json or {}
    return state.get("execution_mode") == "compliance_harness" or state.get("agent_domain") == "compliance"


def _guard_compliance_uses_harness(project: Project) -> None:
    if _is_compliance_project(project):
        raise FXPGError(
            "合规观察案件请使用「运行合规分析」，以确保 CMP 规则与商业交付物完整生成",
            code="USE_HARNESS",
            status=400,
        )


def _guard_server_case_path() -> None:
    if not settings.allow_server_case_path:
        raise FXPGError(
            "服务器路径导入已禁用，请使用浏览器文件夹上传",
            code="PATH_DISABLED",
            status=403,
        )


def _meeting_out(db: Session, meeting: Meeting) -> MeetingOut:
    data = meeting_to_dict(meeting, counts=True, db=db)
    return MeetingOut(**data)


@router.get("/agent/status")
def agent_status():
    from app.services.vision_client import vision_available

    ready = llm_available()
    return {
        "mode": "agent_only",
        "ready": ready,
        "rules_ready": True,
        "full_agent_ready": ready,
        "agent_domain": settings.agent_domain,
        "domain_label": get_domain_pack().label,
        "vision_ready": vision_available(),
        "message": (
            "智能体已就绪"
            if ready
            else "请配置 LLM_API_KEY 并启用 ENABLE_LLM"
        ),
    }


@router.post("/agent/chat", response_model=AgentChatResponse)
def agent_chat(payload: AgentChatRequest, db: Session = Depends(get_db)):
    return run_main_agent_chat(
        db,
        message=payload.message,
        project_id=payload.project_id,
        meeting_id=payload.meeting_id,
        history=payload.history,
    )


@router.post("/agent/actions/{proposal_id}/approve", response_model=AgentActionApproveResponse)
def approve_agent_action_route(
    proposal_id: str,
    payload: Optional[AgentActionApproveRequest] = None,
    db: Session = Depends(get_db),
):
    return approve_agent_action(db, proposal_id, comment=(payload.comment if payload else None))


@router.post("/projects", response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=payload.name, status="active")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if payload.name is not None:
        project.name = payload.name.strip()
    if payload.summary is not None:
        project.summary = payload.summary.strip() or None
    db.commit()
    db.refresh(project)
    return project


@router.post("/projects/batch-delete")
def batch_delete_projects(payload: ProjectBatchDelete, db: Session = Depends(get_db)):
    deleted = 0
    for pid in payload.project_ids:
        if db.get(Project, pid):
            _delete_project_cascade(db, pid)
            deleted += 1
    db.commit()
    return {"ok": True, "deleted": deleted}


@router.get("/projects/{project_id}/meetings", response_model=list[MeetingOut])
def list_project_meetings(project_id: str, db: Session = Depends(get_db)):
    meetings = list_meetings(db, project_id)
    return [_meeting_out(db, m) for m in meetings]


@router.post("/projects/{project_id}/meetings", response_model=MeetingOut)
def create_project_meeting(project_id: str, payload: MeetingCreate, db: Session = Depends(get_db)):
    meeting = create_meeting(
        db,
        project_id,
        meeting_code=payload.meeting_code,
        meeting_title=payload.meeting_title,
        observation_type=payload.observation_type,
        meeting_type=payload.meeting_type,
        meeting_date=payload.meeting_date,
    )
    return _meeting_out(db, meeting)


@router.get("/projects/{project_id}/meetings/{meeting_id}", response_model=MeetingOut)
def get_project_meeting(project_id: str, meeting_id: str, db: Session = Depends(get_db)):
    return _meeting_out(db, get_meeting(db, project_id, meeting_id))


@router.patch("/projects/{project_id}/meetings/{meeting_id}", response_model=MeetingOut)
def patch_project_meeting(
    project_id: str,
    meeting_id: str,
    payload: MeetingUpdate,
    db: Session = Depends(get_db),
):
    meeting = update_meeting(
        db,
        project_id,
        meeting_id,
        meeting_code=payload.meeting_code,
        meeting_title=payload.meeting_title,
        observation_type=payload.observation_type,
        meeting_type=payload.meeting_type,
        meeting_date=payload.meeting_date,
        summary=payload.summary,
    )
    return _meeting_out(db, meeting)


@router.delete("/projects/{project_id}/meetings/{meeting_id}")
def delete_project_meeting(project_id: str, meeting_id: str, db: Session = Depends(get_db)):
    delete_meeting_cascade(db, project_id, meeting_id)
    db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/meetings/batch-delete")
def batch_delete_meetings(
    project_id: str,
    payload: MeetingBatchDelete,
    db: Session = Depends(get_db),
):
    deleted = delete_meetings_batch(db, project_id, payload.meeting_ids)
    return {"ok": True, "deleted": deleted}


@router.get("/projects/{project_id}/meetings/{meeting_id}/live", response_model=ProjectLiveOut)
def get_meeting_live(project_id: str, meeting_id: str, db: Session = Depends(get_db)):
    return build_meeting_live(db, project_id, meeting_id)


@router.get("/projects/{project_id}/meetings/{meeting_id}/jobs/latest", response_model=Optional[JobOut])
def latest_meeting_job(project_id: str, meeting_id: str, db: Session = Depends(get_db)):
    return load_latest_meeting_job(db, project_id, meeting_id)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    return project


@router.get("/projects/{project_id}/live", response_model=ProjectLiveOut)
def get_project_live(project_id: str, db: Session = Depends(get_db)):
    return build_project_live(db, project_id)


@router.get("/projects/{project_id}/overview", response_model=ProjectOverviewOut)
def get_project_overview(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    files = (
        db.query(FileRecord)
        .filter_by(project_id=project_id)
        .order_by(FileRecord.created_at)
        .all()
    )
    risk_preview = (
        db.query(Risk)
        .filter_by(project_id=project_id)
        .order_by(Risk.risk_score.desc())
        .limit(6)
        .all()
    )
    file_count = len(files)
    risk_count = db.query(Risk).filter_by(project_id=project_id).count()
    output_count = primary_output_count(db, project_id=project_id)
    return ProjectOverviewOut(
        id=project.id,
        name=project.name,
        status=project.status,
        summary=project.summary,
        created_at=project.created_at,
        updated_at=project.updated_at,
        state_json=project.state_json,
        file_count=file_count,
        risk_count=risk_count,
        output_count=output_count,
        files=files,
        risk_preview=risk_preview,
    )


@router.get("/projects/{project_id}/files", response_model=list[FileOut])
def list_project_files(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    return (
        db.query(FileRecord)
        .filter_by(project_id=project_id)
        .order_by(FileRecord.created_at)
        .all()
    )


@router.get("/projects/{project_id}/meetings/{meeting_id}/files", response_model=list[FileOut])
def list_meeting_files(project_id: str, meeting_id: str, db: Session = Depends(get_db)):
    get_meeting(db, project_id, meeting_id)
    return (
        db.query(FileRecord)
        .filter_by(project_id=project_id, meeting_id=meeting_id)
        .order_by(FileRecord.created_at)
        .all()
    )


@router.post("/projects/{project_id}/meetings/{meeting_id}/files")
async def upload_meeting_files(
    project_id: str,
    meeting_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    meeting = get_meeting(db, project_id, meeting_id)

    upload_dir = settings.storage_path / "uploads" / project_id / meeting_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    max_bytes = settings.max_upload_mb * 1024 * 1024

    for uf in files:
        if not uf.filename:
            continue
        ext = Path(uf.filename).suffix.lower()
        if ext not in settings.allowed_extensions:
            raise FXPGError(f"不支持的文件类型: {ext}", code="INVALID_FILE_TYPE", status=400)

        dest = upload_dir / uf.filename
        size = 0
        with dest.open("wb") as f:
            while chunk := await uf.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    dest.unlink(missing_ok=True)
                    raise FXPGError(
                        f"文件 {uf.filename} 超过 {settings.max_upload_mb}MB 限制",
                        code="FILE_TOO_LARGE",
                        status=400,
                    )
                f.write(chunk)

        from app.services.classifier import classify_document

        classification = classify_document(uf.filename, ext, domain=resolve_agent_domain(project))
        rec = FileRecord(
            project_id=project_id,
            meeting_id=meeting_id,
            file_name=uf.filename,
            file_type=classification["file_type"],
            document_category=classification["document_category"],
            storage_path=str(dest),
            confidence=classification["confidence"],
            meta_json=classification,
            parse_status="uploaded",
        )
        db.add(rec)
        saved.append(uf.filename)

    meeting.status = "ready"
    project.status = "active"
    db.commit()
    return {"uploaded": saved}


@router.post("/projects/{project_id}/meetings/{meeting_id}/harness/run", response_model=HarnessResultOut)
def harness_run_meeting(
    project_id: str,
    meeting_id: str,
    payload: Optional[HarnessRunRequest] = None,
    db: Session = Depends(get_db),
):
    get_meeting(db, project_id, meeting_id)
    require_agent_llm()
    req = payload or HarnessRunRequest()
    job, created = start_harness_job(
        db, project_id, meeting_id, skip_orchestrator=req.skip_orchestrator
    )
    return HarnessResultOut(
        project_id=project_id,
        meeting_id=meeting_id,
        status="running",
        message="合规分析已启动" if created else "分析任务进行中",
        job_id=job.id,
    )


@router.post("/projects/{project_id}/files")
async def upload_files(
    project_id: str,
    meeting_id: Optional[str] = Query(default=None),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    if not meeting_id:
        meeting_id = ensure_default_meeting(db, project_id).id
    return await upload_meeting_files(project_id, meeting_id, files, db)


@router.post("/projects/{project_id}/analyze", response_model=AnalyzeResponse)
def analyze_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if db.query(FileRecord).filter_by(project_id=project_id).count() == 0:
        raise FXPGError("请先上传资料", code="NO_FILES", status=400)
    if _is_compliance_project(project):
        raise FXPGError(
            "合规观察案件请使用「运行合规分析」，以确保 CMP 规则与商业交付物完整生成",
            code="USE_HARNESS",
            status=400,
        )
    require_agent_llm()

    running = (
        db.query(AnalysisJob)
        .filter_by(project_id=project_id)
        .filter(AnalysisJob.status.in_(["queued", "running"]))
        .first()
    )
    if running:
        return AnalyzeResponse(
            project_id=project_id,
            status="running",
            message="分析任务进行中",
            job_id=running.id,
        )

    job = create_job(db, project_id)
    project.status = "classifying"
    db.commit()
    enqueue_analysis(job.id, project_id)
    return AnalyzeResponse(
        project_id=project_id,
        status="running",
        message="分析任务已加入队列",
        job_id=job.id,
    )


@router.post("/projects/{project_id}/analyze-incremental", response_model=AnalyzeResponse)
def analyze_incremental(project_id: str, db: Session = Depends(get_db)):
    """补资料后增量分析：仅处理新上传文件并重跑受影响阶段。"""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    state = project.state_json or {}
    if not state.get("agent_plan"):
        raise FXPGError("请先完成一次全量分析", code="NO_PRIOR_RUN", status=400)
    _guard_compliance_uses_harness(project)
    require_agent_llm()

    from app.services.agent.incremental_replan import diff_uploaded_files

    files = db.query(FileRecord).filter_by(project_id=project_id).all()
    diff = diff_uploaded_files(state, files)
    if not diff.new_file_ids:
        raise FXPGError("未检测到新增资料，请先上传文件", code="NO_NEW_FILES", status=400)

    running = (
        db.query(AnalysisJob)
        .filter_by(project_id=project_id)
        .filter(AnalysisJob.status.in_(["queued", "running"]))
        .first()
    )
    if running:
        return AnalyzeResponse(
            project_id=project_id,
            status="running",
            message="已有任务进行中",
            job_id=running.id,
        )

    job = create_job(db, project_id)
    project.status = "planning"
    db.commit()
    enqueue_analysis(job.id, project_id, scope="incremental")
    return AnalyzeResponse(
        project_id=project_id,
        status="running",
        message=f"增量分析已启动（新增 {len(diff.new_file_ids)} 份资料）",
        job_id=job.id,
    )


@router.post("/projects/{project_id}/reanalyze", response_model=AnalyzeResponse)
def reanalyze_project(
    project_id: str,
    payload: ReanalyzeRequest,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if payload.scope not in ("cross_checking", "adjudicating"):
        raise FXPGError(
            "scope 须为 cross_checking 或 adjudicating",
            code="INVALID_SCOPE",
            status=400,
        )
    if not (project.state_json or {}).get("agent_plan"):
        raise FXPGError("请先完成一次全量分析", code="NO_PRIOR_RUN", status=400)
    _guard_compliance_uses_harness(project)
    require_agent_llm()

    running = (
        db.query(AnalysisJob)
        .filter_by(project_id=project_id)
        .filter(AnalysisJob.status.in_(["queued", "running"]))
        .first()
    )
    if running:
        return AnalyzeResponse(
            project_id=project_id,
            status="running",
            message="已有任务进行中",
            job_id=running.id,
        )

    job = create_job(db, project_id)
    state = dict(project.state_json or {})
    state["pending_scope"] = payload.scope
    project.state_json = state
    project.status = payload.scope
    db.commit()
    enqueue_analysis(job.id, project_id, scope=payload.scope)
    return AnalyzeResponse(
        project_id=project_id,
        status="running",
        message=f"局部重跑已启动（{payload.scope}）",
        job_id=job.id,
    )


@router.get("/projects/{project_id}/jobs/latest", response_model=Optional[JobOut])
def latest_job(project_id: str, db: Session = Depends(get_db)):
    return load_latest_project_job(db, project_id)


@router.get("/stats", response_model=StatsOut)
def global_stats(db: Session = Depends(get_db)):
    seed_rules(db)
    risks = db.query(Risk).all()
    return StatsOut(
        project_count=db.query(Project).count(),
        risk_count=len(risks),
        rule_count=db.query(Rule).filter_by(enabled=True).count(),
        high_count=sum(1 for r in risks if r.risk_level == "高"),
        medium_count=sum(1 for r in risks if r.risk_level == "中"),
        low_count=sum(1 for r in risks if r.risk_level == "低"),
    )


@router.get("/projects/{project_id}/summary", response_model=ProjectSummary)
def project_summary(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    risks = db.query(Risk).filter_by(project_id=project_id).filter(Risk.status != "dismissed").all()
    missing = (project.state_json or {}).get("missing_documents", [])
    return ProjectSummary(
        total_risks=len(risks),
        high=sum(1 for r in risks if r.risk_level == "高"),
        medium=sum(1 for r in risks if r.risk_level == "中"),
        low=sum(1 for r in risks if r.risk_level == "低"),
        missing_documents=missing,
        correction_suggestions=[r.suggestion for r in risks if r.manual_review_required][:20],
    )


@router.get("/projects/{project_id}/agent-briefs")
def get_agent_briefs(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    state = project.state_json or {}
    from app.services.agent.mcp_hub import parse_mcp_servers

    return {
        "sub_agent_briefs": state.get("sub_agent_briefs") or {},
        "synthesis_brief": state.get("synthesis_brief") or {},
        "mission": state.get("mission") or {},
        "mcp_servers": [c.name for c in parse_mcp_servers()],
        "execution_mode": state.get("execution_mode"),
    }


def _delete_project_cascade(db: Session, project_id: str) -> None:
    """删除项目及全部关联数据（含磁盘 uploads/outputs）。"""
    _delete_project_child_rows(db, project_id)
    db.query(Meeting).filter_by(project_id=project_id).delete(synchronize_session=False)
    for sub in ("uploads", "outputs"):
        path = settings.storage_path / sub / project_id
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    project = db.get(Project, project_id)
    if project:
        db.delete(project)


def _delete_project_child_rows(db: Session, project_id: str) -> None:
    """Delete every project-owned child table before deleting meetings/projects.

    The compliance product evolves by adding audit/evaluation/supplement tables.
    Keeping this dynamic prevents stale cascade lists from breaking batch delete.
    """
    inspector = inspect(db.get_bind())
    ordered = [
        "review_records",
        "supplement_requests",
        "evidence_gaps",
        "audit_check_results",
        "audit_facts",
        "evaluation_runs",
        "audit_runs",
        "agent_action_proposals",
        "agent_run_logs",
        "analysis_jobs",
        "outputs",
        "record_links",
        "extracted_entities",
        "parsed_documents",
        "risks",
        "files",
    ]
    project_tables: list[str] = []
    for table_name in inspector.get_table_names():
        if table_name in {"projects", "meetings"}:
            continue
        columns = {col["name"] for col in inspector.get_columns(table_name)}
        if "project_id" in columns:
            project_tables.append(table_name)

    remaining = sorted(t for t in project_tables if t not in ordered)
    for table_name in [t for t in ordered if t in project_tables] + remaining:
        db.execute(
            text(f'DELETE FROM "{table_name}" WHERE project_id = :project_id'),
            {"project_id": project_id},
        )


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "项目不存在")
    _delete_project_cascade(db, project_id)
    db.commit()
    return {"ok": True}


@router.patch("/rules/{rule_db_id}/toggle")
def toggle_rule(rule_db_id: str, db: Session = Depends(get_db)):
    rule = db.get(Rule, rule_db_id)
    if not rule:
        raise HTTPException(404, "规则不存在")
    rule.enabled = not rule.enabled
    db.commit()
    return {"ok": True, "enabled": rule.enabled}


@router.get("/projects/{project_id}/meetings/{meeting_id}/risks", response_model=list[RiskOut])
def list_meeting_risks(
    project_id: str,
    meeting_id: str,
    level: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    get_meeting(db, project_id, meeting_id)
    q = db.query(Risk).filter_by(project_id=project_id, meeting_id=meeting_id)
    if level:
        q = q.filter(Risk.risk_level == level)
    return q.order_by(Risk.risk_score.desc()).all()


@router.get("/projects/{project_id}/meetings/{meeting_id}/outputs")
def list_meeting_outputs(project_id: str, meeting_id: str, db: Session = Depends(get_db)):
    get_meeting(db, project_id, meeting_id)
    return primary_outputs(db, project_id=project_id, meeting_id=meeting_id)


@router.get("/projects/{project_id}/meetings/{meeting_id}/logs", response_model=list)
def list_meeting_logs(project_id: str, meeting_id: str, db: Session = Depends(get_db)):
    return load_meeting_logs(db, project_id, meeting_id)


@router.post("/projects/{project_id}/meetings/{meeting_id}/regenerate-outputs")
def regenerate_meeting_outputs(project_id: str, meeting_id: str, db: Session = Depends(get_db)):
    get_meeting(db, project_id, meeting_id)
    if db.query(Risk).filter_by(project_id=project_id, meeting_id=meeting_id).count() == 0:
        raise FXPGError("请先完成分析", code="NO_RISKS", status=400)
    AgentWorkflow(db, project_id, meeting_id=meeting_id).regenerate_outputs_only()
    return {"ok": True, "message": "交付物已重新生成"}


@router.post("/projects/{project_id}/meetings/{meeting_id}/reanalyze", response_model=AnalyzeResponse)
def reanalyze_meeting(
    project_id: str,
    meeting_id: str,
    payload: ReanalyzeRequest,
    db: Session = Depends(get_db),
):
    meeting = get_meeting(db, project_id, meeting_id)
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if payload.scope not in ("cross_checking", "adjudicating"):
        raise FXPGError(
            "scope 须为 cross_checking 或 adjudicating",
            code="INVALID_SCOPE",
            status=400,
        )
    if not (meeting.state_json or {}).get("agent_plan"):
        raise FXPGError("请先完成一次全量分析", code="NO_PRIOR_RUN", status=400)
    _guard_compliance_uses_harness(project)
    require_agent_llm()

    running = (
        db.query(AnalysisJob)
        .filter_by(project_id=project_id, meeting_id=meeting_id)
        .filter(AnalysisJob.status.in_(["queued", "running"]))
        .first()
    )
    if running:
        return AnalyzeResponse(
            project_id=project_id,
            status="running",
            message="已有任务进行中",
            job_id=running.id,
        )

    job = create_job(db, project_id, meeting_id=meeting_id)
    state = dict(meeting.state_json or {})
    state["pending_scope"] = payload.scope
    meeting.state_json = state
    meeting.status = payload.scope
    db.commit()
    enqueue_analysis(job.id, project_id, scope=payload.scope)
    return AnalyzeResponse(
        project_id=project_id,
        status="running",
        message=f"局部重跑已启动（{payload.scope}）",
        job_id=job.id,
    )


@router.post("/projects/{project_id}/meetings/{meeting_id}/deliverables/accept")
def accept_meeting_deliverables_route(project_id: str, meeting_id: str, db: Session = Depends(get_db)):
    meeting = accept_meeting_deliverables(db, project_id, meeting_id)
    return {"ok": True, "status": meeting.status}


@router.post("/projects/{project_id}/meetings/{meeting_id}/deliverables/reject")
def reject_meeting_deliverables_route(
    project_id: str,
    meeting_id: str,
    payload: DeliverableReview,
    db: Session = Depends(get_db),
):
    meeting = get_meeting(db, project_id, meeting_id)
    comment = payload.comment or ""

    if payload.reanalyze:
        require_agent_llm()
        running = (
            db.query(AnalysisJob)
            .filter_by(project_id=project_id, meeting_id=meeting_id)
            .filter(AnalysisJob.status.in_(["queued", "running"]))
            .first()
        )
        if running:
            return {
                "ok": True,
                "status": "running",
                "message": "已有分析任务进行中",
                "job_id": running.id,
            }
        state = dict(meeting.state_json or {})
        state["deliverable"] = {"status": "pending", "comment": comment}
        if comment:
            state["deliverable_feedback"] = comment
            plan = dict(state.get("agent_plan") or {})
            plan["deliverable_feedback"] = comment
            state["agent_plan"] = plan
        meeting.state_json = state
        meeting.status = "planning"
        db.commit()
        job = create_job(db, project_id, meeting_id=meeting_id)
        agent_domain = state.get("agent_domain") or settings.agent_domain
        execution_mode = state.get("execution_mode")
        if execution_mode == "compliance_harness" or agent_domain == "compliance":
            enqueue_harness(job.id, project_id, meeting_id)
        else:
            enqueue_analysis(job.id, project_id, scope="full")
        sync_project_rollups(db, project_id)
        return {
            "ok": True,
            "status": "running",
            "message": "已根据退回意见重新分析",
            "job_id": job.id,
        }

    meeting = reject_meeting_deliverables(db, project_id, meeting_id, comment)
    return {"ok": True, "status": meeting.status, "comment": comment}


@router.get("/projects/{project_id}/risks", response_model=list[RiskOut])
def list_risks(
    project_id: str,
    level: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    q = db.query(Risk).filter_by(project_id=project_id)
    if level:
        q = q.filter(Risk.risk_level == level)
    return q.order_by(Risk.risk_score.desc()).all()


@router.post("/projects/{project_id}/risks/{risk_id}/review")
def review_risk(
    project_id: str,
    risk_id: str,
    payload: ReviewCreate,
    db: Session = Depends(get_db),
):
    risk = db.query(Risk).filter_by(project_id=project_id, id=risk_id).first()
    if not risk:
        raise HTTPException(404, "风险不存在")
    risk.status = payload.review_status
    review = ReviewRecord(
        project_id=project_id,
        risk_id=risk.id,
        review_status=payload.review_status,
        review_comment=payload.review_comment,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    write_review_memory(db, risk, review)

    pending = (
        db.query(Risk)
        .filter_by(project_id=project_id)
        .filter(Risk.status == "pending", Risk.manual_review_required.is_(True))
        .count()
    )
    project = db.get(Project, project_id)
    if project and project.status == "needs_review" and pending == 0:
        project.status = "completed"
        db.commit()

    return {"ok": True, "pending_reviews": pending}


@router.post("/projects/{project_id}/regenerate-outputs")
def regenerate_outputs(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if db.query(Risk).filter_by(project_id=project_id).count() == 0:
        raise FXPGError("请先完成分析", code="NO_RISKS", status=400)
    AgentWorkflow(db, project_id).regenerate_outputs_only()
    return {"ok": True, "message": "交付物已重新生成"}


@router.post("/projects/{project_id}/deliverables/accept")
def accept_deliverables(project_id: str, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "项目不存在")
    meeting = ensure_default_meeting(db, project_id)
    return accept_meeting_deliverables_route(project_id, meeting.id, db)


@router.post("/projects/{project_id}/deliverables/reject")
def reject_deliverables(
    project_id: str,
    payload: DeliverableReview,
    db: Session = Depends(get_db),
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "项目不存在")
    meeting = ensure_default_meeting(db, project_id)
    return reject_meeting_deliverables_route(project_id, meeting.id, payload, db)


@router.get("/projects/{project_id}/outputs")
def list_outputs(project_id: str, db: Session = Depends(get_db)):
    return primary_outputs(db, project_id=project_id)


@router.get("/projects/{project_id}/outputs/{output_id}/download")
def download_output(
    project_id: str,
    output_id: str,
    api_key: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    from app.config import settings

    if settings.api_key:
        if api_key != settings.api_key:
            raise HTTPException(401, "无效的 API Key")
    output = db.query(Output).filter_by(project_id=project_id, id=output_id).first()
    if not output:
        raise HTTPException(404, "交付物不存在")
    path = Path(output.storage_path)
    if not path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(path, filename=output.file_name)


@router.get("/projects/{project_id}/logs", response_model=list)
def list_logs(project_id: str, db: Session = Depends(get_db)):
    return load_project_logs(db, project_id)


@router.get("/rules", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db)):
    seed_rules(db)
    return db.query(Rule).order_by(Rule.priority.desc()).all()


@router.post("/rules", response_model=RuleOut)
def create_rule(payload: RuleCreate, db: Session = Depends(get_db)):
    if db.query(Rule).filter_by(rule_id=payload.rule_id).first():
        raise FXPGError("规则 ID 已存在", code="RULE_EXISTS", status=409)
    rule = Rule(
        rule_id=payload.rule_id,
        rule_name=payload.rule_name,
        risk_category=payload.risk_category,
        risk_level=payload.risk_level,
        applicable_document_type=payload.applicable_document_type,
        condition_json=payload.condition,
        evidence_fields=payload.evidence_fields,
        suggestion_template=payload.suggestion_template,
        manual_review_required=payload.manual_review_required,
        priority=payload.priority,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.post("/memories/reindex")
def reindex_memories(db: Session = Depends(get_db)):
    from app.services.seed import reindex_memory_vectors

    count = reindex_memory_vectors(db)
    return {"ok": True, "reindexed": count}


@router.get("/memories/search")
def search_memories(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    from app.services.memory_rag import retrieve_memories

    seed_memories(db)
    results = retrieve_memories(db, query_text=q, limit=limit)
    return [{"id": m.id, "memory_type": m.memory_type, "content": m.content, "tags": m.tags} for m in results]


@router.get("/memories", response_model=list[MemoryOut])
def list_memories(db: Session = Depends(get_db)):
    seed_memories(db)
    return db.query(Memory).order_by(Memory.created_at.desc()).all()


@router.post("/memories", response_model=MemoryOut)
def create_memory(payload: MemoryCreate, db: Session = Depends(get_db)):
    from app.services.embedding_service import embed_memory_content

    mem = Memory(
        memory_type=payload.memory_type,
        content=payload.content,
        tags=payload.tags,
        embedding_json=embed_memory_content(payload.content, payload.tags),
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    from app.services.vector_store import sync_memory_vector

    if mem.embedding_json:
        sync_memory_vector(db, mem.id, mem.embedding_json)
        db.commit()
    return mem


@router.post("/harness/import", response_model=HarnessResultOut)
def harness_import_case(payload: HarnessImportRequest, db: Session = Depends(get_db)):
    """从服务器本地案件目录导入观察资料（需 ALLOW_SERVER_CASE_PATH=true）。"""
    _guard_server_case_path()
    from app.services.agent.harness import ComplianceHarness

    case_path = Path(payload.case_path).expanduser().resolve()
    if not case_path.is_dir():
        raise FXPGError(f"案件目录不存在: {case_path}", code="CASE_NOT_FOUND", status=400)

    harness = ComplianceHarness(db)
    project_id, meeting_id, profile = harness.import_case(case_path, payload.project_name)
    return HarnessResultOut(
        project_id=project_id,
        meeting_id=meeting_id,
        status="imported",
        meeting_code=str(profile.get("meeting_code") or ""),
        finding_count=0,
        meeting_case=profile,
    )


@router.post("/projects/{project_id}/harness/import-upload", response_model=HarnessResultOut)
async def harness_import_project_upload(
    project_id: str,
    files: list[UploadFile] = File(...),
    meeting_title: Optional[str] = Form(None),
    run_analysis: bool = Form(default=True),
    db: Session = Depends(get_db),
):
    """向已有观察项目导入 FX 资料包：新建子会议、入库，可选立即运行分析。"""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    from app.services.agent.harness import ComplianceHarness
    from app.services.domain.compliance.case_upload import cleanup_staged_case, stage_case_upload

    case_dir = await stage_case_upload(files)
    try:
        harness = ComplianceHarness(db)
        pid, meeting_id, profile = harness.import_case(
            case_dir, meeting_title, project_id=project_id
        )
        if run_analysis:
            require_agent_llm()
            job, created = start_harness_job(db, pid, meeting_id)
            return HarnessResultOut(
                project_id=pid,
                meeting_id=meeting_id,
                status="running",
                message="已导入并启动分析" if created else "分析任务进行中",
                job_id=job.id,
                meeting_code=str(profile.get("meeting_code") or ""),
                finding_count=0,
                meeting_case=profile,
            )
        return HarnessResultOut(
            project_id=pid,
            meeting_id=meeting_id,
            status="imported",
            meeting_code=str(profile.get("meeting_code") or ""),
            finding_count=0,
            meeting_case=profile,
        )
    finally:
        cleanup_staged_case(case_dir)


@router.post("/harness/import-upload", response_model=HarnessResultOut)
async def harness_import_case_upload(
    files: list[UploadFile] = File(...),
    project_name: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """从浏览器选择文件夹上传并导入案件。"""
    from app.services.agent.harness import ComplianceHarness
    from app.services.domain.compliance.case_upload import cleanup_staged_case, stage_case_upload

    case_dir = await stage_case_upload(files)
    try:
        harness = ComplianceHarness(db)
        project_id, meeting_id, profile = harness.import_case(case_dir, project_name)
        return HarnessResultOut(
            project_id=project_id,
            meeting_id=meeting_id,
            status="imported",
            meeting_code=str(profile.get("meeting_code") or ""),
            finding_count=0,
            meeting_case=profile,
        )
    finally:
        cleanup_staged_case(case_dir)


@router.post("/harness/run-case-upload", response_model=HarnessResultOut)
async def harness_run_case_upload(
    files: list[UploadFile] = File(...),
    project_name: Optional[str] = Form(None),
    skip_orchestrator: bool = Form(False),
    db: Session = Depends(get_db),
):
    """从浏览器选择文件夹上传、导入并异步运行 Harness。"""
    from app.services.agent.harness import ComplianceHarness
    from app.services.domain.compliance.case_upload import cleanup_staged_case, stage_case_upload

    case_dir = await stage_case_upload(files)
    try:
        harness = ComplianceHarness(db)
        project_id, meeting_id, profile = harness.import_case(case_dir, project_name)
        job, created = start_harness_job(
            db,
            project_id,
            meeting_id,
            skip_orchestrator=skip_orchestrator,
        )
        return HarnessResultOut(
            project_id=project_id,
            meeting_id=meeting_id,
            status="running",
            message="已导入并启动 Harness" if created else "Harness 任务进行中",
            job_id=job.id,
            meeting_code=str(profile.get("meeting_code") or ""),
            finding_count=0,
            meeting_case=profile,
        )
    finally:
        cleanup_staged_case(case_dir)


@router.post("/projects/{project_id}/harness/run", response_model=HarnessResultOut)
def harness_run_project(
    project_id: str,
    payload: Optional[HarnessRunRequest] = None,
    db: Session = Depends(get_db),
):
    """对已导入项目异步运行合规 Agent Harness（返回 job_id，前端轮询实时进度）。"""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if db.query(FileRecord).filter_by(project_id=project_id).count() == 0:
        raise FXPGError("请先导入或上传资料", code="NO_FILES", status=400)

    require_agent_llm()
    req = payload or HarnessRunRequest()
    meeting_id = req.meeting_id
    if not meeting_id:
        meeting = (
            db.query(Meeting)
            .filter_by(project_id=project_id)
            .order_by(Meeting.updated_at.desc())
            .first()
        )
        if not meeting:
            meeting = ensure_default_meeting(db, project_id)
        meeting_id = meeting.id
    job, created = start_harness_job(
        db, project_id, meeting_id, skip_orchestrator=req.skip_orchestrator
    )
    return HarnessResultOut(
        project_id=project_id,
        meeting_id=meeting_id,
        status="running",
        message="Harness 已启动，请查看顶部运行管线" if created else "Harness 任务进行中",
        job_id=job.id,
    )


@router.post("/harness/run-case", response_model=HarnessResultOut)
def harness_run_case(payload: HarnessImportRequest, db: Session = Depends(get_db)):
    """导入 FX 案件目录并异步运行 Harness（需 ALLOW_SERVER_CASE_PATH=true）。"""
    _guard_server_case_path()
    from app.services.agent.harness import ComplianceHarness

    case_path = Path(payload.case_path).expanduser().resolve()
    if not case_path.is_dir():
        raise FXPGError(f"案件目录不存在: {case_path}", code="CASE_NOT_FOUND", status=400)

    harness = ComplianceHarness(db)
    project_id, meeting_id, profile = harness.import_case(case_path, payload.project_name)
    job, created = start_harness_job(db, project_id, meeting_id)
    return HarnessResultOut(
        project_id=project_id,
        meeting_id=meeting_id,
        status="running",
        message="已导入并启动 Harness" if created else "Harness 任务进行中",
        job_id=job.id,
        meeting_code=str(profile.get("meeting_code") or ""),
        finding_count=0,
        meeting_case=profile,
    )
