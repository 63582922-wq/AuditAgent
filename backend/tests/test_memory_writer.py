"""Tests for agent memory write decisions."""

from app.models import Project, Risk
from app.services.agent.memory_writer import decide_and_persist_memories


def _sample_project(db) -> Project:
    project = Project(name="Memory writer test", status="completed")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def test_decide_and_persist_skips_low_confidence(db):
    sample_project = _sample_project(db)
    db.add(
        Risk(
            project_id=sample_project.id,
            meeting_id=None,
            risk_id="R1",
            risk_category="test",
            risk_level="高",
            risk_score=90,
            problem="p",
            evidence_json={},
            suggestion="s",
            analysis="a",
            confidence=0.5,
            status="pending",
        )
    )
    db.commit()
    summary = decide_and_persist_memories(db, sample_project.id)
    assert summary.written == 0


def test_decide_and_persist_writes_high_confidence(db):
    sample_project = _sample_project(db)
    db.add(
        Risk(
            project_id=sample_project.id,
            meeting_id=None,
            risk_id="R2",
            risk_category="CMP",
            risk_level="高",
            risk_score=95,
            problem="签到缺失",
            evidence_json={},
            suggestion="补签到",
            analysis="证据不足",
            confidence=0.9,
            status="pending",
            manual_review_required=False,
        )
    )
    db.commit()
    summary = decide_and_persist_memories(db, sample_project.id, limit=5)
    assert summary.written >= 1
