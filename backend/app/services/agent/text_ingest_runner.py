from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agent.mission_planner import MissionTask

if TYPE_CHECKING:
    from app.services.agent.agent_trace import AgentTrace
    from app.services.agent.pipeline_executor import PipelineExecutor


class TextIngestRunner:
    """文本 Ingest Worker：资料分拣、PDF/Excel 解析与实体抽取（非 LLM 主 Agent）。"""

    @staticmethod
    def execute_task(task: MissionTask, executor: "PipelineExecutor", trace: "AgentTrace") -> None:
        trace.log(
            "orchestrator",
            "running",
            kind="text_ingest",
            name=task.assignee_name,
            message=task.title,
            detail={
                "task_id": task.id,
                "objective": task.objective,
                "steps": task.pipeline_steps,
            },
        )
        for step in task.pipeline_steps:
            if step not in executor.state["completed_steps"]:
                executor.execute_step(step)
        trace.log(
            "orchestrator",
            "completed",
            kind="text_ingest",
            name=task.assignee_name,
            message=f"完成：{task.title}",
            detail={"task_id": task.id},
        )
