from app.services.agent.modality_router import is_vision_file, split_files_by_modality, VISION_AGENT_ID
from app.services.agent.mission_planner import build_default_mission
from app.services.domain.compliance.compliance_vision import normalize_compliance_vision


class _File:
    def __init__(self, name: str, file_type: str = "pdf", category: str = "unknown"):
        self.file_name = name
        self.file_type = file_type
        self.document_category = category


def test_split_modality():
    files = [
        _File("a.pdf", "pdf", "a1_meeting_export"),
        _File("b.jpg", "image", "meeting_screenshot"),
    ]
    text, vision = split_files_by_modality(files)
    assert len(text) == 1
    assert len(vision) == 1
    assert is_vision_file(files[1])


def test_mission_includes_vision_task():
    files = [_File("x.jpg", "image", "sign_in_record")]
    mission = build_default_mission(files, {"sub_agents": [], "focus_areas": []})
    assignees = [t.assignee for t in mission.tasks]
    assert VISION_AGENT_ID in assignees
    assert "classifying" in mission.tasks[0].pipeline_steps


def test_normalize_compliance_vision():
    fields = normalize_compliance_vision(
        {"summary_text": "确认单", "reasoning": "时长15分钟", "confidence": 0.9, "speaker_service_minutes": 12},
        "observation_confirmation",
    )
    assert fields["speaker_service_minutes"] == 12
    assert fields["vision_reasoning"] == "时长15分钟"
