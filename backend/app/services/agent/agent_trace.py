from __future__ import annotations

import inspect
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from sqlalchemy.orm import Session

from app.models import AgentRunLog


def trace_code_location(skip_modules: set[str] | None = None) -> dict[str, Any]:
    """Return the first non-trace caller so UI logs can point to code-level origin."""
    skip_modules = skip_modules or set()
    root = Path(__file__).resolve().parents[4]
    for frame in inspect.stack()[1:]:
        module = frame.frame.f_globals.get("__name__", "")
        if module == __name__ or module in skip_modules:
            continue
        filename = Path(frame.filename).resolve()
        try:
            rel = filename.relative_to(root)
        except ValueError:
            rel = filename
        return {
            "file": str(rel),
            "line": frame.lineno,
            "function": frame.function,
            "module": module,
        }
    return {}


class AgentTrace:
    """结构化 Agent 执行追踪，写入 agent_run_logs。"""

    def __init__(self, db: Session, project_id: str, meeting_id: str | None = None):
        self.db = db
        self.project_id = project_id
        self.meeting_id = meeting_id

    def log(
        self,
        step: str,
        status: str,
        *,
        kind: str = "step",
        name: str = "",
        message: str = "",
        detail: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        payload: Dict[str, Any] = {"kind": kind, "name": name or step, "message": message}
        if detail:
            payload.update(detail)
        payload.setdefault("code_location", trace_code_location())
        self.db.add(
            AgentRunLog(
                project_id=self.project_id,
                meeting_id=self.meeting_id,
                step=step,
                status=status,
                detail_json=payload,
                duration_ms=duration_ms,
            )
        )
        self.db.commit()

    def step(self, step: str, status: str, detail: Optional[Dict[str, Any]] = None) -> None:
        self.log(step, status, kind="step", detail=detail)

    def tool(
        self,
        tool_name: str,
        status: str,
        *,
        message: str = "",
        detail: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        self.log(
            "tool",
            status,
            kind="tool",
            name=tool_name,
            message=message,
            detail=detail,
            duration_ms=duration_ms,
        )

    def plan(self, plan: Dict[str, Any], graph: Dict[str, Any]) -> None:
        self.log(
            "planning",
            "completed",
            kind="plan",
            message=graph.get("agent_message", ""),
            detail={"plan": plan, "execution_graph": graph},
        )

    @contextmanager
    def timed_step(self, step: str) -> Iterator[None]:
        started = time.time()
        self.step(step, "running")
        try:
            yield
            self.step(step, "completed", {"duration_ms": int((time.time() - started) * 1000)})
        except Exception as exc:
            self.step(step, "failed", {"error": str(exc), "duration_ms": int((time.time() - started) * 1000)})
            raise
