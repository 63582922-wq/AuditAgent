from __future__ import annotations

from app.models import FileRecord
from app.services.agent.mission_planner import build_default_mission


def test_build_default_mission_accepts_structured_focus_items(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "agent_domain", "compliance")
    files = [
        FileRecord(
            id="file-1",
            project_id="project-1",
            meeting_id="meeting-1",
            file_name="Remote_SMS202606090070_线上截图.jpg",
            file_type="image",
            document_category="meeting_screenshot",
            storage_path="/tmp/shot.jpg",
            parse_status="uploaded",
        )
    ]

    mission = build_default_mission(
        files,
        {
            "focus_areas": [{"title": "参会人数核实", "reason": "需和端口截图比对"}],
            "priority_actions": [{"action": "核实最大端口数"}],
        },
    )

    assert "参会人数核实" in mission.objective
    assert any(task.assignee == "vision_agent" for task in mission.tasks)
