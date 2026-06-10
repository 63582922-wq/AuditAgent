import json

import pytest

from app.models import FileRecord, Project
from app.services.agent.pipeline_executor import PipelineExecutor
from app.services.agent.pipeline_tools import STEP_DEPENDENCIES


def test_step_dependencies_chain():
    assert "classifying" in STEP_DEPENDENCIES["parsing"]
    assert "running_rules" in STEP_DEPENDENCIES["adjudicating"]


def test_executor_observation(db, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "agent_execution_mode", "pipeline")

    p = Project(name="react-test", status="created")
    db.add(p)
    db.commit()
    db.refresh(p)

    db.add(
        FileRecord(
            project_id=p.id,
            file_name="a.csv",
            file_type="excel",
            document_category="expense_detail",
            storage_path="/tmp/a.csv",
            parse_status="uploaded",
        )
    )
    db.commit()

    ex = PipelineExecutor(db, p.id)
    ex.state["agent_plan"] = {"focus_areas": ["税务风险"], "sub_agents": []}
    ex.state["file_count"] = 1
    ex.state["completed_steps"] = set()

    obs = ex.get_observation()
    assert obs["file_count"] == 1
    assert obs["completed_steps"] == []


def test_react_loop_mock(db, monkeypatch):
    from app.config import settings
    from app.services.agent.react_loop import run_react_loop
    from app.services.agent.pipeline_executor import PipelineExecutor

    monkeypatch.setattr(settings, "react_max_turns", 12)

    p = Project(name="react-mock", status="created")
    db.add(p)
    db.commit()

    ex = PipelineExecutor(db, p.id)
    ex.state = {
        "completed_steps": set(),
        "agent_plan": {"focus_areas": [], "sub_agents": [{"name": "税务专员"}]},
        "graph": None,
        "files": [],
        "file_count": 0,
        "parsed_docs": [],
        "all_risks": [],
        "entities": [],
        "links": [],
    }

    steps_run = []

    def fake_execute(step):
        steps_run.append(step)
        ex.state["completed_steps"].add(step)
        return {"step": step, "ok": True}

    ex.execute_step = fake_execute  # type: ignore

    sequence = [
        {"tool_calls": [{"id": "1", "function": {"name": "run_step", "arguments": json.dumps({"step": "classifying", "reason": "t"})}}]},
        {"tool_calls": [{"id": "2", "function": {"name": "run_step", "arguments": json.dumps({"step": "parsing", "reason": "t"})}}]},
        {"tool_calls": [{"id": "3", "function": {"name": "run_step", "arguments": json.dumps({"step": "extracting", "reason": "t"})}}]},
        {"tool_calls": [{"id": "4", "function": {"name": "run_step", "arguments": json.dumps({"step": "running_rules", "reason": "t"})}}]},
        {"tool_calls": [{"id": "5", "function": {"name": "run_step", "arguments": json.dumps({"step": "adjudicating", "reason": "t"})}}]},
        {"tool_calls": [{"id": "6", "function": {"name": "run_step", "arguments": json.dumps({"step": "generating_report", "reason": "t"})}}]},
        {"tool_calls": [{"id": "7", "function": {"name": "finish_analysis", "arguments": json.dumps({"summary": "done"})}}]},
    ]
    call_i = {"n": 0}

    def fake_chat(messages, tools=None, tool_choice=None, temperature=0.2):
        i = call_i["n"]
        call_i["n"] += 1
        if i < len(sequence):
            return {"role": "assistant", **sequence[i]}
        return {"role": "assistant", "content": "done"}

    monkeypatch.setattr("app.services.agent.react_loop.chat_completion", fake_chat)

    class FakeTrace:
        def log(self, *a, **k):
            pass

        def tool(self, *a, **k):
            pass

    result = run_react_loop(ex, FakeTrace())
    assert "classifying" in result["completed_steps"]
    assert "generating_report" in result["completed_steps"]
