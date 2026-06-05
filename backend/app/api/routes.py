from __future__ import annotations

import shutil
from pathlib import Path

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.config import settings
from app.database import get_db
from app.exceptions import FXPGError
from app.models import AgentRunLog, AnalysisJob, FileRecord, Memory, Output, Project, ReviewRecord, Risk, Rule
from app.schemas import (
    AnalyzeResponse,
    JobOut,
    MemoryCreate,
    MemoryOut,
    ProjectCreate,
    ProjectDetail,
    ProjectOut,
    ProjectSummary,
    ReviewCreate,
    RiskOut,
    RuleCreate,
    RuleOut,
    StatsOut,
)
from app.services.agent.workflow import AgentWorkflow
from app.config import settings
from app.services.agent.llm_client import llm_available, require_agent_llm
from app.services.jobs.worker import create_job, enqueue_analysis
from app.services.seed import seed_memories, seed_rules

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/agent/status")
def agent_status():
    from app.services.vision_client import vision_available

    ready = llm_available()
    return {
        "mode": "agent_only",
        "ready": ready,
        "text_model": settings.llm_model,
        "text_base_url": settings.text_base_url,
        "vision_model": settings.vision_model,
        "vision_ready": vision_available(),
        "message": (
            "智能体已就绪"
            if ready
            else "请配置 LLM_API_KEY（DeepSeek）与 ENABLE_LLM=true"
        ),
    }


@router.post("/projects", response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=payload.name, status="created")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    return project


@router.post("/projects/{project_id}/files")
async def upload_files(
    project_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")

    upload_dir = settings.storage_path / "uploads" / project_id
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

        rec = FileRecord(
            project_id=project_id,
            file_name=uf.filename,
            file_type="unknown",
            storage_path=str(dest),
            parse_status="uploaded",
        )
        db.add(rec)
        saved.append(uf.filename)

    project.status = "uploaded"
    db.commit()
    return {"uploaded": saved}


@router.post("/projects/{project_id}/analyze", response_model=AnalyzeResponse)
def analyze_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if db.query(FileRecord).filter_by(project_id=project_id).count() == 0:
        raise FXPGError("请先上传资料", code="NO_FILES", status=400)
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


@router.get("/projects/{project_id}/jobs/latest", response_model=JobOut)
def latest_job(project_id: str, db: Session = Depends(get_db)):
    job = (
        db.query(AnalysisJob)
        .filter_by(project_id=project_id)
        .order_by(AnalysisJob.created_at.desc())
        .first()
    )
    if not job:
        raise HTTPException(404, "暂无分析任务")
    return job


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


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    db.delete(project)
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
    db.add(
        ReviewRecord(
            project_id=project_id,
            risk_id=risk.id,
            review_status=payload.review_status,
            review_comment=payload.review_comment,
        )
    )
    db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/regenerate-outputs")
def regenerate_outputs(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if db.query(Risk).filter_by(project_id=project_id).count() == 0:
        raise FXPGError("请先完成分析", code="NO_RISKS", status=400)
    AgentWorkflow(db, project_id).regenerate_outputs_only()
    return {"ok": True, "message": "交付物已重新生成"}


@router.get("/projects/{project_id}/outputs")
def list_outputs(project_id: str, db: Session = Depends(get_db)):
    return db.query(Output).filter_by(project_id=project_id).all()


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


@router.get("/projects/{project_id}/logs")
def list_logs(project_id: str, db: Session = Depends(get_db)):
    return db.query(AgentRunLog).filter_by(project_id=project_id).order_by(AgentRunLog.created_at).all()


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
