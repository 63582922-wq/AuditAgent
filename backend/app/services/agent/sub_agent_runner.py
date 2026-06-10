from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agent.mission_planner import MissionTask
from app.services.agent.sub_agent_loop import run_main_synthesis_brief, run_sub_agent_session

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.agent.agent_trace import AgentTrace
    from app.services.agent.pipeline_executor import PipelineExecutor


class MainAgentRunner:
    @staticmethod
    def execute_task(task: MissionTask, executor: PipelineExecutor, trace: AgentTrace) -> None:
        trace.log(
            "orchestrator",
            "running",
            kind="main_agent",
            name=task.assignee_name,
            message=task.title,
            detail={"task_id": task.id, "objective": task.objective, "steps": task.pipeline_steps},
        )

        if task.id == "synthesis" or "adjudicating" in task.pipeline_steps:
            briefs = executor.state.get("sub_agent_briefs") or {}
            plan = dict(executor.state.get("agent_plan") or {})
            plan["sub_agent_briefs"] = briefs
            synthesis = run_main_synthesis_brief(executor, trace, task)
            plan["synthesis_brief"] = synthesis
            executor.state["agent_plan"] = plan
            executor.state["synthesis_brief"] = synthesis

        for step in task.pipeline_steps:
            if step not in executor.state["completed_steps"]:
                executor.execute_step(step)

        trace.log(
            "orchestrator",
            "completed",
            kind="main_agent",
            name=task.assignee_name,
            message=f"完成：{task.title}",
            detail={"task_id": task.id},
        )


class SubAgentRunner:
    @staticmethod
    def execute_task(
        task: MissionTask,
        executor: PipelineExecutor,
        trace: AgentTrace,
        skill_text: str,
        db: Session,
        project_id: str,
    ) -> None:
        brief = run_sub_agent_session(db, project_id, task, skill_text, executor, trace)
        briefs = dict(executor.state.get("sub_agent_briefs") or {})
        briefs[task.assignee] = brief
        executor.state["sub_agent_briefs"] = briefs
