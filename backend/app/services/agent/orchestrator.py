from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from sqlalchemy.orm import Session

from app.models import FileRecord, Project
from app.services.agent.meeting_scope import scoped_query
from app.services.agent.agent_trace import AgentTrace
from app.services.agent.execution_graph import ExecutionGraph
from app.services.agent.llm_client import require_agent_llm
from app.services.agent.mission_planner import decompose_mission
from app.services.agent.skill_registry import load_skill
from app.services.agent.pipeline_executor import PipelineExecutor
from app.services.agent.sub_agent_runner import MainAgentRunner, SubAgentRunner
from app.services.agent.modality_router import TEXT_INGEST_AGENT_ID, VISION_AGENT_ID
from app.services.agent.text_ingest_runner import TextIngestRunner
from app.services.agent.vision_agent_runner import VisionAgentRunner


class MissionOrchestrator:
    """主 Agent：拆解任务 → 委派子 Agent → 汇总交付。"""

    def __init__(
        self,
        db: Session,
        project_id: str,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        trace: Optional[AgentTrace] = None,
        meeting_id: Optional[str] = None,
    ):
        self.db = db
        self.project_id = project_id
        self.meeting_id = meeting_id
        self.progress_callback = progress_callback
        self.trace = trace or AgentTrace(db, project_id, meeting_id)

    def run(self) -> Dict[str, Any]:
        require_agent_llm()
        project = self.db.get(Project, self.project_id)
        if not project:
            raise ValueError("project not found")

        files = scoped_query(self.db, FileRecord, self.project_id, self.meeting_id).all()
        if not files:
            raise ValueError("请先上传资料")

        self.trace.step("orchestrator", "running", {"mode": "orchestrator", "file_count": len(files)})

        prior_state = project.state_json or {}
        prior_plan = dict(prior_state.get("agent_plan") or {})
        feedback = prior_state.get("deliverable_feedback") or (prior_state.get("deliverable") or {}).get("comment")
        if feedback:
            prior_plan["deliverable_feedback"] = feedback

        mission = decompose_mission(self.db, self.project_id, files, agent_plan=prior_plan or None)
        self.trace.log(
            "orchestrator",
            "planned",
            kind="mission",
            message=mission.objective,
            detail=mission.to_dict(),
        )

        executor = PipelineExecutor(
            self.db,
            self.project_id,
            self.progress_callback,
            self.trace,
            self.meeting_id,
        )
        graph = ExecutionGraph.from_plan(mission.agent_plan, files)
        self.trace.plan(mission.agent_plan, graph.to_dict())
        executor.state.update(
            {
                "agent_plan": mission.agent_plan,
                "graph": graph,
                "files": files,
                "file_count": len(files),
                "sub_agent_briefs": prior_state.get("sub_agent_briefs") or {},
            }
        )

        for task in mission.tasks:
            if task.assignee == "main":
                MainAgentRunner.execute_task(task, executor, self.trace)
            elif task.assignee == VISION_AGENT_ID:
                VisionAgentRunner.execute_task(task, executor, self.trace)
            elif task.assignee == TEXT_INGEST_AGENT_ID:
                TextIngestRunner.execute_task(task, executor, self.trace)
            else:
                skill = load_skill(task.assignee)
                SubAgentRunner.execute_task(
                    task, executor, self.trace, skill, self.db, self.project_id
                )

        executor.finalize(execution_mode="orchestrator", mission=mission.to_dict())
        return {"mode": "orchestrator", "tasks": len(mission.tasks), "risk_count": len(executor.state.get("all_risks") or [])}
