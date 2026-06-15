from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, List

from app.config import settings
from app.exceptions import FXPGError
from app.models import FileRecord, ParsedDocument
from app.services.agent.modality_router import is_vision_file
from app.services.agent.mission_planner import MissionTask

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
        vision_files = [f for f in files if is_vision_file(f)]
        parsed_docs = list(executor.state.get("parsed_docs") or [])
        count = 0
        delay_sec = max(settings.vision_inter_request_delay_sec, 0.0)
        made_request = False

        executor.wf._set_status(project, "parsing")
        for f in vision_files:
            if f.parse_status == "done":
                continue

            if made_request and delay_sec > 0:
                time.sleep(delay_sec)
            made_request = True

            path = Path(f.storage_path)
            category = f.document_category or "unknown"

            trace.log(
                "vision_agent",
                "running",
                kind="vision_agent",
                name="视觉 Agent",
                message=f"读图 {f.file_name}",
                detail={"file_name": f.file_name, "category": category},
            )

            def on_retry(attempt: int, max_retries: int, wait_sec: float, reason: str, file_name: str = f.file_name) -> None:
                trace.log(
                    "vision_agent",
                    "running",
                    kind="vision_agent",
                    name="视觉 Agent",
                    message=f"限流重试 {file_name}（{attempt}/{max_retries}，等待 {wait_sec:.1f}s）",
                    detail={
                        "file_name": file_name,
                        "retry_attempt": attempt,
                        "retry_max": max_retries,
                        "wait_sec": round(wait_sec, 1),
                        "reason": reason,
                    },
                )

            try:
                if pack.name == "compliance":
                    content = analyze_compliance_image(
                        path, category, f.file_name, on_retry=on_retry
                    )
                else:
                    content = parse_image(path)
                    content["vision_agent"] = True
            except FXPGError as exc:
                trace.log(
                    "vision_agent",
                    "failed",
                    kind="vision_agent",
                    name="视觉 Agent",
                    message=f"读图失败 {f.file_name}: {exc.message}",
                    detail={
                        "file_name": f.file_name,
                        "category": category,
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
                    message=f"读图失败 {f.file_name}: {exc}",
                    detail={
                        "file_name": f.file_name,
                        "category": category,
                        "error": str(exc),
                        "code": "VISION_LLM_FAILED",
                    },
                )
                raise

            pd = ParsedDocument(
                project_id=executor.project_id,
                file_id=f.id,
                document_type=f.document_category,
                content_json=content,
                text_content=content.get("text_content", ""),
            )
            executor.db.merge(pd)
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
                },
            )

        executor.state["parsed_docs"] = parsed_docs
        return count
