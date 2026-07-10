from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from app.models import AgentRunLog, CaseRun, Meeting


def build_run_events_snapshot(
    db: Session,
    *,
    project_id: str,
    meeting_id: str,
    run: CaseRun | None,
) -> dict[str, Any]:
    logs = (
        db.query(AgentRunLog)
        .filter_by(project_id=project_id, meeting_id=meeting_id)
        .order_by(AgentRunLog.created_at.asc())
        .all()
    )
    if run:
        logs = [log for log in logs if (log.detail_json or {}).get("run_id") == run.id]

    meeting = db.get(Meeting, meeting_id)
    terminal_success = bool(
        (run and run.status in {"completed", "needs_review", "accepted"})
        or (not run and meeting and meeting.status in {"completed", "needs_review", "accepted"})
    )
    events: list[dict[str, Any]] = []
    for log in logs:
        detail = dict(log.detail_json or {})
        raw_status = log.status
        normalized_status = raw_status
        # Older trace producers emitted start events without a matching close
        # event. Once the owning CaseRun is terminal, keep the raw value for
        # audit but make the graph's lifecycle state honest and non-sticky.
        if terminal_success and raw_status in {"running", "planned"}:
            normalized_status = "completed_inferred"
            detail["raw_status"] = raw_status
            detail["terminal_inferred"] = True
        kind = str(detail.get("kind") or "step")
        category = {
            "vision_agent": "evidence",
            "text_ingest": "evidence",
            "evidence": "evidence",
            "tool": "tool",
            "memory": "memory",
            "critic": "validation",
            "evaluation": "validation",
            "validation": "validation",
            "runtime": "system",
            "harness": "system",
            "chat": "agent",
        }.get(kind, "agent")
        severity = "error" if normalized_status in {"failed", "error"} else "warning" if normalized_status == "skipped" else "info"
        events.append(
            {
                "id": log.id,
                "step": log.step,
                "status": normalized_status,
                "kind": kind,
                "category": category,
                "severity": severity,
                "name": str(detail.get("name") or log.step),
                "message": str(detail.get("message") or detail.get("error") or ""),
                "duration_ms": log.duration_ms,
                "created_at": log.created_at.isoformat() + "Z" if log.created_at else None,
                "detail": detail,
            }
        )

    statuses = Counter(event["status"] for event in events)
    categories = Counter(event["category"] for event in events)
    failed = sum(1 for event in events if event["status"] in {"failed", "error"})
    running = sum(1 for event in events if event["status"] in {"running", "planned"})
    health = "blocked" if failed else "running" if running else "healthy" if events else "idle"
    return {
        "available": bool(run),
        "version": run.id if run else "",
        "project_id": project_id,
        "meeting_id": meeting_id,
        "summary": {
            "event_count": len(events),
            "tool_event_count": sum(1 for event in events if event["category"] == "tool"),
            "failed_event_count": failed,
            "running_event_count": running,
            "open_running_event_count": running,
            "skipped_event_count": statuses.get("skipped", 0),
            "duration_ms_total": sum(int(event["duration_ms"] or 0) for event in events),
            "status_counts": dict(statuses),
            "category_counts": dict(categories),
            "first_event_at": events[0]["created_at"] if events else None,
            "last_event_at": events[-1]["created_at"] if events else None,
        },
        "health": {
            "level": health,
            "signals": (["failed_events"] if failed else []) + (["running_events"] if running else []),
        },
        "events": events,
    }
