from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Meeting, Project, Risk
from app.services.agent.agent_trace import AgentTrace
from app.services.agent.critic_readjudicate import run_critic_readjudicate_loop
from app.services.agent.human_gate import HumanGateResult, evaluate_human_gate
from app.services.agent.meeting_scope import scoped_query
from app.services.agent.memory_writer import decide_and_persist_memories
from app.services.agent.workflow import AgentWorkflow


@dataclass
class RuntimeResult:
    scope: str
    status: str
    human_gate: Dict[str, Any] = field(default_factory=dict)
    critic_summary: Dict[str, Any] = field(default_factory=dict)
    memories_written: int = 0


class AgentRuntime:
    """Agent 外环：工作流执行 → Critic 重研判 → 记忆写回 → 交付门禁。"""

    SCOPES = ("full", "cross_checking", "adjudicating", "incremental")

    def __init__(
        self,
        db: Session,
        project_id: str,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        meeting_id: Optional[str] = None,
    ):
        self.db = db
        self.project_id = project_id
        self.meeting_id = meeting_id
        self.progress_callback = progress_callback
        self.trace = AgentTrace(db, project_id, meeting_id)

    def _state_host(self) -> tuple[Project, Optional[Meeting], dict]:
        project = self.db.get(Project, self.project_id)
        if not project:
            raise ValueError("project not found")
        meeting = self.db.get(Meeting, self.meeting_id) if self.meeting_id else None
        if meeting:
            return project, meeting, dict(meeting.state_json or {})
        return project, None, dict(project.state_json or {})

    def run(self, scope: str = "full") -> RuntimeResult:
        if scope not in self.SCOPES:
            raise ValueError(f"unsupported scope: {scope}")

        workflow = AgentWorkflow(self.db, self.project_id, self.progress_callback, meeting_id=self.meeting_id)
        if scope == "full":
            mode = settings.agent_execution_mode
            if mode == "react":
                workflow.run_react()
            elif mode == "orchestrator":
                workflow.run_orchestrator()
            else:
                workflow.run()
        elif scope == "incremental":
            workflow.run_incremental()
        else:
            workflow.run_partial(scope)

        return self._post_process(scope)

    def _post_process(self, scope: str) -> RuntimeResult:
        project, meeting, state = self._state_host()

        plan = state.get("agent_plan") or {}
        critic_loop = run_critic_readjudicate_loop(self.db, self.project_id, self.trace, plan)

        flagged = critic_loop.flagged
        self.trace.log(
            "critic",
            "completed",
            kind="critic",
            message=f"校验 {critic_loop.validated} 条，剩余疑点 {flagged} 条"
            + (
                f"（自动重研判 {critic_loop.readjudicate_rounds} 轮）"
                if critic_loop.readjudicate_rounds
                else ""
            ),
            detail={
                "validated": critic_loop.validated,
                "flagged": flagged,
                "readjudicate_rounds": critic_loop.readjudicate_rounds,
                "outputs_regenerated": critic_loop.outputs_regenerated,
                "samples": [
                    {"risk_id": c.risk_id, "message": c.message}
                    for c in critic_loop.critic_results
                    if not c.valid
                ][:5],
            },
        )

        risks = scoped_query(self.db, Risk, self.project_id, self.meeting_id).filter(
            Risk.status != "dismissed"
        ).all()
        critic_flag_count = sum(1 for c in critic_loop.critic_results if not c.valid)

        feedback = state.get("deliverable_feedback") or (state.get("deliverable") or {}).get("comment")
        memory_summary = decide_and_persist_memories(
            self.db,
            self.project_id,
            self.meeting_id,
            critic_results=critic_loop.critic_results,
            deliverable_feedback=feedback if isinstance(feedback, str) else None,
        )
        memories_written = memory_summary.written
        if memories_written:
            self.trace.log(
                "memory",
                "completed",
                kind="memory",
                message=f"Agent 沉淀 {memories_written} 条长期记忆",
                detail={"written": memories_written, "types": memory_summary.types},
            )

        status_host = meeting if meeting else project
        if settings.enable_human_gate:
            gate = evaluate_human_gate(risks, critic_flag_count=critic_flag_count)
            if gate.pause and status_host.status == "completed":
                status_host.status = "needs_review"
                self.db.commit()
        else:
            gate = HumanGateResult(
                pause=False,
                reason="Agent 自检完成，请验收交付物",
                manual_count=sum(1 for r in risks if r.manual_review_required),
                total_count=len(risks),
                critic_flag_count=critic_flag_count,
            )

        state["runtime"] = {
            "scope": scope,
            "execution_mode": settings.agent_execution_mode if scope == "full" else scope,
            "human_gate": {
                "pause": gate.pause,
                "reason": gate.reason,
                "manual_count": gate.manual_count,
                "total_count": gate.total_count,
                "critic_flag_count": gate.critic_flag_count,
            },
            "critic": {
                "validated": critic_loop.validated,
                "flagged": flagged,
                "readjudicate_rounds": critic_loop.readjudicate_rounds,
                "outputs_regenerated": critic_loop.outputs_regenerated,
                "llm_enabled": settings.enable_critic_llm,
            },
            "memories_written": memories_written,
            "memory_decision": memory_summary.types,
        }
        if meeting:
            meeting.state_json = state
        else:
            project.state_json = state
        self.db.commit()

        domain = state.get("agent_domain") or settings.agent_domain
        if domain == "compliance":
            AgentWorkflow(
                self.db, self.project_id, self.progress_callback, meeting_id=self.meeting_id
            ).regenerate_outputs_only()

        self.trace.log(
            "runtime",
            "completed" if not gate.pause else "needs_review",
            kind="runtime",
            message=gate.reason,
            detail=state["runtime"],
        )

        return RuntimeResult(
            scope=scope,
            status=status_host.status,
            human_gate=state["runtime"]["human_gate"],
            critic_summary=state["runtime"]["critic"],
            memories_written=memories_written,
        )
