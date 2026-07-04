from __future__ import annotations

from pathlib import Path
import threading
import time

from PIL import Image
from types import SimpleNamespace

from app.models import FileRecord
from app.exceptions import FXPGError
from app.services.agent.vision_agent_runner import VisionAgentRunner


class _Trace:
    def __init__(self) -> None:
        self.records = []

    def log(self, *args, **kwargs) -> None:
        self.records.append((args, kwargs))


class _Db:
    def __init__(self) -> None:
        self.merged = []
        self.commits = 0

    def merge(self, obj):
        self.merged.append(obj)

    def add(self, obj):
        self.merged.append(obj)

    def query(self, model):
        db = self

        class _Query:
            def __init__(self) -> None:
                self.file_id = None

            def filter_by(self, **kwargs):
                self.file_id = kwargs.get("file_id")
                return self

            def one_or_none(self):
                for obj in db.merged:
                    if getattr(obj, "file_id", None) == self.file_id:
                        return obj
                return None

        return _Query()

    def commit(self) -> None:
        self.commits += 1


class _Workflow:
    def _set_status(self, project, status: str) -> None:
        project.status = status


class _Project:
    status = "active"


class _Executor:
    def __init__(self, file_record: FileRecord | list[FileRecord]) -> None:
        files = file_record if isinstance(file_record, list) else [file_record]
        self.project = _Project()
        self.project_id = "project-1"
        self.meeting_id = "meeting-1"
        self.db = _Db()
        self.wf = _Workflow()
        self.state = {"files": files, "parsed_docs": []}


def test_vision_runner_reclassifies_and_reruns_ambiguous_image(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "image001.jpg"
    Image.new("RGB", (900, 900), "white").save(image_path)
    file_record = FileRecord(
        id="file-1",
        project_id="project-1",
        meeting_id="meeting-1",
        file_name="image001.jpg",
        file_type="image",
        document_category="meeting_screenshot",
        confidence=0.4,
        storage_path=str(image_path),
        parse_status="uploaded",
    )
    executor = _Executor(file_record)
    calls = []

    def fake_analyze(path, category, file_name, **kwargs):
        calls.append(category)
        return {
            "file_type": "image",
            "document_type": category,
            "ocr_engine": "vision:test",
            "text_content": "现场确认单\\n本场会议是否成功观察：是\\n共计 45 分钟",
            "fields": {"vision_confidence": 0.9},
            "confidence": {"vision_confidence": 0.9},
            "bbox": [],
            "vision_agent": True,
        }

    monkeypatch.setattr(
        "app.services.domain.compliance.compliance_vision.analyze_compliance_image",
        fake_analyze,
    )
    monkeypatch.setattr(
        "app.services.domain.registry.get_domain_pack",
        lambda *args, **kwargs: SimpleNamespace(name="compliance"),
    )

    count = VisionAgentRunner.parse_vision_files(executor, _Trace())

    assert count == 1
    assert calls == ["meeting_screenshot", "observation_confirmation"]
    assert file_record.document_category == "observation_confirmation"
    assert file_record.confidence >= 0.75
    assert executor.state["parsed_docs"][0]["document_category"] == "observation_confirmation"
    assert executor.db.merged[0].meeting_id == "meeting-1"


def test_vision_runner_parses_multiple_images_concurrently(tmp_path: Path, monkeypatch) -> None:
    files = []
    for idx in range(3):
        image_path = tmp_path / f"image{idx}.jpg"
        Image.new("RGB", (900, 900), "white").save(image_path)
        files.append(
            FileRecord(
                id=f"file-{idx}",
                project_id="project-1",
                meeting_id="meeting-1",
                file_name=f"image{idx}.jpg",
                file_type="image",
                document_category="presentation_material",
                confidence=0.8,
                storage_path=str(image_path),
                parse_status="uploaded",
            )
        )
    executor = _Executor(files)
    lock = threading.Lock()
    active = 0
    max_active = 0

    def fake_analyze(path, category, file_name, **kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.08)
        with lock:
            active -= 1
        return {
            "file_type": "image",
            "document_type": category,
            "ocr_engine": "vision:test",
            "text_content": "PPT材料",
            "fields": {"vision_confidence": 0.9},
            "confidence": {"vision_confidence": 0.9},
            "bbox": [],
            "vision_agent": True,
        }

    monkeypatch.setattr(
        "app.services.domain.compliance.compliance_vision.analyze_compliance_image",
        fake_analyze,
    )
    monkeypatch.setattr(
        "app.services.domain.registry.get_domain_pack",
        lambda *args, **kwargs: SimpleNamespace(name="compliance"),
    )
    monkeypatch.setattr("app.services.agent.vision_agent_runner.settings.vision_max_workers", 3, raising=False)
    monkeypatch.setattr(
        "app.services.agent.vision_agent_runner.settings.vision_inter_request_delay_sec",
        0,
    )

    count = VisionAgentRunner.parse_vision_files(executor, _Trace())

    assert count == 3
    assert max_active >= 2
    assert [doc.meeting_id for doc in executor.db.merged] == ["meeting-1", "meeting-1", "meeting-1"]


def test_vision_runner_logs_consensus_and_manual_review_status(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "sign.jpg"
    Image.new("RGB", (900, 900), "white").save(image_path)
    file_record = FileRecord(
        id="file-sign",
        project_id="project-1",
        meeting_id="meeting-1",
        file_name="sign.jpg",
        file_type="image",
        document_category="sign_in_record",
        confidence=0.8,
        storage_path=str(image_path),
        parse_status="uploaded",
    )
    executor = _Executor(file_record)
    trace = _Trace()

    def fake_analyze(path, category, file_name, **kwargs):
        return {
            "file_type": "image",
            "document_type": category,
            "ocr_engine": "vision:test",
            "text_content": "签到表 6人",
            "fields": {"vision_confidence": 0.9, "actual_sign_in_count": 6},
            "confidence": {"vision_confidence": 0.9, "actual_sign_in_count": 0.86},
            "manual_review_required": True,
            "review_reasons": ["single_pass_high_risk_document"],
            "vision_consensus": {
                "status": "needs_review",
                "manual_review_required": True,
                "review_reasons": ["single_pass_high_risk_document"],
            },
            "bbox": [],
            "vision_agent": True,
        }

    monkeypatch.setattr(
        "app.services.domain.compliance.compliance_vision.analyze_compliance_image",
        fake_analyze,
    )
    monkeypatch.setattr(
        "app.services.domain.registry.get_domain_pack",
        lambda *args, **kwargs: SimpleNamespace(name="compliance"),
    )

    count = VisionAgentRunner.parse_vision_files(executor, trace)

    assert count == 1
    completed = [
        kwargs["detail"]
        for args, kwargs in trace.records
        if args == ("vision_agent", "completed")
    ]
    assert completed
    assert completed[-1]["manual_review_required"] is True
    assert completed[-1]["review_reasons"] == ["single_pass_high_risk_document"]
    assert completed[-1]["vision_consensus_status"] == "needs_review"


def test_vision_runner_keeps_rate_limited_file_pending_without_failing_run(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "limited.jpg"
    Image.new("RGB", (900, 900), "white").save(image_path)
    file_record = FileRecord(
        id="file-limited",
        project_id="project-1",
        meeting_id="meeting-1",
        file_name="limited.jpg",
        file_type="image",
        document_category="meeting_screenshot",
        confidence=0.8,
        storage_path=str(image_path),
        parse_status="uploaded",
    )
    executor = _Executor(file_record)
    trace = _Trace()

    def fake_analyze(*args, **kwargs):
        raise FXPGError("视觉模型限流（429），已重试 5 次", code="VISION_RATE_LIMITED", status=429)

    monkeypatch.setattr(
        "app.services.domain.compliance.compliance_vision.analyze_compliance_image",
        fake_analyze,
    )
    monkeypatch.setattr(
        "app.services.domain.registry.get_domain_pack",
        lambda *args, **kwargs: SimpleNamespace(name="compliance"),
    )

    count = VisionAgentRunner.parse_vision_files(executor, trace)

    assert count == 0
    assert file_record.parse_status == "pending"
    assert file_record.meta_json["vision_error"]["code"] == "VISION_RATE_LIMITED"
    assert executor.state["parsed_docs"] == []
    assert any(args[1] == "skipped" for args, _ in trace.records)
