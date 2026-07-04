from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import fitz
from PIL import Image

from app.services.agent.workflow import AgentWorkflow
from app.services.parsers.pdf_ingest_splitter import (
    MIN_PAGE_TEXT_CHARS,
    _classify_page,
    ingest_pdf_hybrid,
)


def _write_text_pdf(path: Path, lines: list[str]) -> None:
    doc = fitz.open()
    for line in lines:
        page = doc.new_page()
        page.insert_text((72, 72), line * 20)
    doc.save(path)
    doc.close()


def _write_scanned_like_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    img = Image.new("RGB", (400, 200), color=(240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(path)
    doc.close()


def test_classify_text_page_vs_scanned_page(tmp_path: Path):
    rich_path = tmp_path / "rich.pdf"
    _write_text_pdf(rich_path, ["会议议程内容 " * 20])

    scan = fitz.open()
    scan_page = scan.new_page()
    img = Image.new("RGB", (300, 300), color=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    scan_page.insert_image(scan_page.rect, stream=buf.getvalue())

    with fitz.open(rich_path) as rich_doc:
        rich_mode, rich_work = _classify_page(rich_doc[0], rich_doc, 1)
    scan_mode, scan_work = _classify_page(scan_page, scan, 1)

    assert rich_mode == "text_only"
    assert rich_work == []
    assert scan_mode == "vision_page"
    assert len(scan_work) == 1
    assert scan_work[0].ingest_mode == "vision_page"

    scan.close()


def test_ingest_text_pdf_no_vision(tmp_path: Path):
    pdf = tmp_path / "agenda.pdf"
    _write_text_pdf(pdf, ["会议议程 " * 30])

    result = ingest_pdf_hybrid(pdf, "meeting_agenda", "agenda.pdf", analyze_vision=False)
    assert result.pdf_type == "text"
    assert result.ingest_mode == "text"
    assert result.vision_slices == []
    assert len(result.text_content.strip()) > MIN_PAGE_TEXT_CHARS


def test_ingest_scanned_pdf_queues_vision_page(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    _write_scanned_like_pdf(pdf)

    calls = []

    def fake_analyze(image, document_category, file_name, **kwargs):
        calls.append(kwargs.get("ingest_mode"))
        return {
            "file_type": "image",
            "text_content": "签到表",
            "fields": {"actual_sign_in_count": 5},
            "ocr_engine": "vision:test",
        }

    monkeypatch.setattr(
        "app.services.parsers.pdf_ingest_splitter._analyze_slice_compliance",
        fake_analyze,
    )

    result = ingest_pdf_hybrid(pdf, "sign_in_record", "scan.pdf", domain="compliance")
    assert result.pdf_type == "scanned"
    assert result.ingest_mode == "vision_only"
    assert len(result.vision_slices) == 1
    assert calls == ["vision_page"]
    assert result.vision_slices[0]["content_json"]["fields"]["actual_sign_in_count"] == 5


def test_compliance_key_text_pdf_still_queues_page_vision_review(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "a1.pdf"
    _write_text_pdf(pdf, ["A1 Platform 会议编号：A1P260307357 会议人数：总人数：7 " * 12])

    calls = []

    def fake_analyze(image, document_category, file_name, **kwargs):
        calls.append((document_category, kwargs.get("ingest_mode")))
        return {
            "file_type": "image",
            "text_content": "视觉复核：A1 会议导出页面",
            "fields": {"meeting_code": "A1P260307357"},
            "ocr_engine": "vision:test",
        }

    monkeypatch.setattr(
        "app.services.parsers.pdf_ingest_splitter._analyze_slice_compliance",
        fake_analyze,
    )

    result = ingest_pdf_hybrid(pdf, "a1_meeting_export", "a1.pdf", domain="compliance")

    assert result.pdf_type == "hybrid"
    assert result.ingest_mode == "hybrid"
    assert len(result.vision_slices) == 1
    assert calls == [("a1_meeting_export", "vision_page_review")]
    assert result.vision_slices[0]["content_json"]["fields"]["meeting_code"] == "A1P260307357"


def test_workflow_logs_pdf_vision_slices_as_vision_agent_event():
    events = []

    class Trace:
        def log(self, *args, **kwargs):
            events.append((args, kwargs))

    workflow = AgentWorkflow.__new__(AgentWorkflow)
    file_record = SimpleNamespace(id="file-1", file_name="scan.pdf", document_category="sign_in_record")
    content = {
        "file_type": "pdf",
        "pdf_type": "scanned",
        "ingest_mode": "vision_only",
        "ocr_engine": "vision:test",
        "vision_slices": [
            {"page_number": 1, "ingest_mode": "vision_page"},
            {"page_number": 2, "ingest_mode": "vision_page"},
        ],
    }

    workflow._log_pdf_vision_slices(Trace(), file_record, content)

    assert len(events) == 1
    args, kwargs = events[0]
    assert args == ("vision_agent", "completed")
    assert kwargs["kind"] == "vision_agent"
    assert kwargs["message"] == "PDF 图像页识别 scan.pdf"
    assert kwargs["detail"]["vision_slice_count"] == 2
    assert kwargs["detail"]["vision_page_count"] == 2
    assert kwargs["detail"]["pdf_type"] == "scanned"
