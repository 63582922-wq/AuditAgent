from __future__ import annotations

from app.models import FileRecord
from app.services.domain.compliance.sub_agents import route_sub_agents


def test_route_sub_agents_accepts_structured_plan_items() -> None:
    files = [
        FileRecord(
            id="file-1",
            project_id="project-1",
            meeting_id="meeting-1",
            file_name="Remote_SMS202606090070_线上直播观看数据.xlsx",
            file_type="excel",
            document_category="sign_in_record",
            storage_path="/tmp/watch.xlsx",
            parse_status="uploaded",
        )
    ]
    plan = {
        "focus_areas": [{"title": "参会人数核实", "reason": "观看记录需和端口截图比对"}],
        "priority_actions": [{"action": "核实 ZOOM 最大端口数"}],
    }

    agents = route_sub_agents(files, plan)

    assert agents
    assert agents[0]["id"] == "attendance"
