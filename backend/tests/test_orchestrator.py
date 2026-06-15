"""Orchestrator 任务拆解与子 Agent 委派测试。"""

from app.models import FileRecord
from app.services.agent.mission_planner import build_default_mission, decompose_mission
from app.services.agent.skill_registry import load_skill


def test_load_skill_tax():
    text = load_skill("tax")
    assert "税务" in text


def test_build_default_mission_structure():
    files = [
        FileRecord(file_name="exp.csv", document_category="expense_detail", confidence=0.9),
        FileRecord(file_name="inv.csv", document_category="invoice_list", confidence=0.9),
    ]
    plan = {
        "focus_areas": ["税务风险", "票据风险"],
        "reasoning": "测试",
        "sub_agents": [
            {"id": "tax", "name": "税务专员", "station": "税务席", "agent_say": "税务", "score": 10},
            {"id": "invoice", "name": "票据专员", "station": "票据席", "agent_say": "票据", "score": 12},
        ],
    }
    mission = build_default_mission(files, plan)
    assert mission.tasks[0].assignee == "text_ingest"
    assert mission.tasks[0].pipeline_steps == ["classifying"]
    text_parse = next(t for t in mission.tasks if t.id == "text_ingest")
    assert text_parse.pipeline_steps == ["parsing", "extracting"]
    assert mission.tasks[-1].assignee == "main"
    assert mission.tasks[-1].pipeline_steps == ["adjudicating", "generating_report"]
    assignees = [t.assignee for t in mission.tasks]
    assert "main" in assignees
    assert any(a in ("invoice", "tax") for a in assignees)


def test_decompose_mission_without_llm_enhance(db, monkeypatch):
    from app.models import Project

    project = Project(name="orch-test", status="created")
    db.add(project)
    db.commit()

    files = [
        FileRecord(
            project_id=project.id,
            file_name="exp.csv",
            file_type="csv",
            storage_path="/tmp/exp.csv",
            document_category="expense_detail",
            confidence=0.9,
        )
    ]
    db.add_all(files)
    db.commit()

    plan = {
        "steps": ["parse", "extract", "run_rules"],
        "focus_areas": ["税务风险"],
        "missing_documents": [],
        "priority_actions": [],
        "reasoning": "mock plan",
        "sub_agents": [{"id": "tax", "name": "税务专员", "station": "税务席", "agent_say": "x", "score": 5}],
        "agent_mode": "agent",
    }

    mission = decompose_mission(
        db,
        project.id,
        files,
        agent_plan=plan,
        use_llm_enhance=False,
    )
    assert mission.objective
    assert len(mission.tasks) >= 4
    assert mission.agent_plan["agent_mode"] == "agent"
