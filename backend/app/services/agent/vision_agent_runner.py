from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, List

from app.config import settings
from app.exceptions import FXPGError
from app.models import FileRecord
from app.services.agent.modality_router import is_vision_file
from app.services.agent.mission_planner import MissionTask
from app.services.parsed_document_store import upsert_parsed_document

if TYPE_CHECKING:
    from app.services.agent.agent_trace import AgentTrace
    from app.services.agent.pipeline_executor import PipelineExecutor


class VisionAgentRunner:
    """视觉 Agent（GLM）：专责图片读图、推理与结构化字段抽取。"""

    @staticmethod
    def execute_task(task: MissionTask, executor: "PipelineExecutor", trace: "AgentTrace") -> None:
        trace.log(
            "orchestrator",
            "running",
            kind="vision_agent",
            name=task.assignee_name,
            message=task.title,
            detail={
                "task_id": task.id,
                "objective": task.objective,
                "model": settings.vision_model,
                "steps": task.pipeline_steps,
            },
        )
        for step in task.pipeline_steps:
            if step not in executor.state["completed_steps"]:
                executor.execute_step(step)
        trace.log(
            "orchestrator",
            "completed",
            kind="vision_agent",
            name=task.assignee_name,
            message=f"完成：{task.title}",
            detail={"task_id": task.id},
        )

    @staticmethod
    def parse_vision_files(executor: "PipelineExecutor", trace: "AgentTrace") -> int:
        from app.services.domain.compliance.compliance_vision import analyze_compliance_image
        from app.services.domain.registry import get_domain_pack
        from app.services.parsers.image_parser import parse_image

        pack = get_domain_pack()
        project = executor.project
        files: List[FileRecord] = executor.state["files"]
        vision_files = [f for f in files if is_vision_file(f) and f.parse_status != "done"]
        parsed_docs = list(executor.state.get("parsed_docs") or [])
        count = 0
        delay_sec = max(settings.vision_inter_request_delay_sec, 0.0)
        max_workers = max(1, min(int(settings.vision_max_workers or 1), len(vision_files) or 1))
        file_by_id = {f.id: f for f in vision_files}

        executor.wf._set_status(project, "parsing")
        jobs: list[dict[str, Any]] = []
        for f in vision_files:
            category = f.document_category or "unknown"
            jobs.append(
                {
                    "file_id": f.id,
                    "file_name": f.file_name,
                    "storage_path": f.storage_path,
                    "category": category,
                    "confidence": f.confidence,
                }
            )
            trace.log(
                "vision_agent",
                "running",
                kind="vision_agent",
                name="视觉 Agent",
                message=f"读图 {f.file_name}",
                detail={"file_name": f.file_name, "category": category},
            )

        def parse_one(job: dict[str, Any]) -> dict[str, Any]:
            path = Path(job["storage_path"])
            category = job["category"]
            retry_events: list[dict[str, Any]] = []

            def on_retry(attempt: int, max_retries: int, wait_sec: float, reason: str) -> None:
                retry_events.append(
                    {
                        "file_name": job["file_name"],
                        "retry_attempt": attempt,
                        "retry_max": max_retries,
                        "wait_sec": round(wait_sec, 1),
                        "reason": reason,
                    }
                )

            previous_category = category
            corrected: dict[str, Any] | None = None
            try:
                if pack.name == "compliance":
                    content = analyze_compliance_image(
                        path, category, job["file_name"], on_retry=on_retry
                    )
                    from app.services.domain.compliance.classifier import reclassify_vision_from_text

                    corrected = reclassify_vision_from_text(
                        file_name=job["file_name"],
                        ext=path.suffix.lower(),
                        current_category=category,
                        current_confidence=job["confidence"],
                        text=content.get("text_content") or "",
                    )
                    if corrected:
                        category = corrected["document_category"]
                        content = analyze_compliance_image(
                            path, category, job["file_name"], on_retry=on_retry
                        )
                        content["reclassified_from"] = previous_category
                else:
                    content = parse_image(path)
                    content["vision_agent"] = True
            except Exception:
                raise

            return {
                "file_id": job["file_id"],
                "file_name": job["file_name"],
                "category": category,
                "previous_category": previous_category,
                "corrected": corrected,
                "content": content,
                "retry_events": retry_events,
            }

        future_map = {}

        def is_rate_limited(exc: FXPGError) -> bool:
            marker = f"{exc.code} {exc.message}".lower()
            return exc.status == 429 or "429" in marker or "限流" in marker or "rate" in marker

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for idx, job in enumerate(jobs):
                if idx > 0 and delay_sec > 0:
                    time.sleep(delay_sec)
                future_map[pool.submit(parse_one, job)] = job

            for future in as_completed(future_map):
                job = future_map[future]
                try:
                    result = future.result()
                except FXPGError as exc:
                    if is_rate_limited(exc):
                        f = file_by_id[job["file_id"]]
                        meta = dict(f.meta_json or {})
                        meta["vision_error"] = {
                            "code": exc.code,
                            "message": exc.message,
                            "manual_review_required": True,
                            "recoverable": True,
                        }
                        f.meta_json = meta
                        f.parse_status = "pending"
                        executor.db.commit()
                        trace.log(
                            "vision_agent",
                            "skipped",
                            kind="vision_agent",
                            name="视觉 Agent",
                            message=f"读图暂缓 {job['file_name']}: {exc.message}",
                            detail={
                                "file_name": job["file_name"],
                                "category": job["category"],
                                "error": exc.message,
                                "code": exc.code,
                                "manual_review_required": True,
                                "recoverable": True,
                            },
                        )
                        continue
                    trace.log(
                        "vision_agent",
                        "failed",
                        kind="vision_agent",
                        name="视觉 Agent",
                        message=f"读图失败 {job['file_name']}: {exc.message}",
                        detail={
                            "file_name": job["file_name"],
                            "category": job["category"],
                            "error": exc.message,
                            "code": exc.code,
                        },
                    )
                    raise
                except Exception as exc:
                    trace.log(
                        "vision_agent",
                        "failed",
                        kind="vision_agent",
                        name="视觉 Agent",
                        message=f"读图失败 {job['file_name']}: {exc}",
                        detail={
                            "file_name": job["file_name"],
                            "category": job["category"],
                            "error": str(exc),
                            "code": "VISION_LLM_FAILED",
                        },
                    )
                    raise

                f = file_by_id[result["file_id"]]
                category = result["category"]
                content = result["content"]
                corrected = result.get("corrected")

                for retry in result.get("retry_events") or []:
                    trace.log(
                        "vision_agent",
                        "running",
                        kind="vision_agent",
                        name="视觉 Agent",
                        message=(
                            f"限流重试 {retry['file_name']}（{retry['retry_attempt']}/"
                            f"{retry['retry_max']}，等待 {retry['wait_sec']:.1f}s）"
                        ),
                        detail=retry,
                    )

                if corrected:
                    previous_category = result["previous_category"]
                    f.document_category = category
                    f.confidence = corrected["confidence"]
                    f.meta_json = corrected
                    trace.log(
                        "vision_agent",
                        "running",
                        kind="vision_agent",
                        name="视觉 Agent",
                        message=f"OCR 后重分类 {f.file_name}: {previous_category} -> {category}",
                        detail={
                            "file_name": f.file_name,
                            "previous_category": previous_category,
                            "category": category,
                            "confidence": corrected["confidence"],
                        },
                    )
                else:
                    f.document_category = category

                upsert_parsed_document(
                    executor.db,
                    project_id=executor.project_id,
                    meeting_id=executor.meeting_id,
                    file_id=f.id,
                    document_type=f.document_category,
                    content_json=content,
                    text_content=content.get("text_content", ""),
                )
                f.parse_status = "done"
                executor.db.commit()

                parsed_docs.append(
                    {
                        "file_id": f.id,
                        "file_name": f.file_name,
                        "document_category": f.document_category,
                        "content_json": content,
                        "text_content": content.get("text_content", ""),
                    }
                )
                count += 1
                consensus = content.get("vision_consensus") if isinstance(content.get("vision_consensus"), dict) else {}
                trace.log(
                    "vision_agent",
                    "completed",
                    kind="vision_agent",
                    name="视觉 Agent",
                    message=f"读图 {f.file_name}",
                    detail={
                        "file_name": f.file_name,
                        "category": category,
                        "confidence": (content.get("fields") or {}).get("vision_confidence"),
                        "engine": content.get("ocr_engine"),
                        "manual_review_required": bool(content.get("manual_review_required")),
                        "review_reasons": content.get("review_reasons") or [],
                        "vision_consensus_status": consensus.get("status"),
                        "vision_consensus_conflicts": consensus.get("conflicts") or [],
                    },
                )

        executor.state["parsed_docs"] = parsed_docs
        return count
