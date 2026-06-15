from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import FileRecord, Meeting, Project, Risk
from app.services.agent.agent_trace import AgentTrace
from app.services.agent.orchestrator import MissionOrchestrator
from app.services.agent.runtime import AgentRuntime
from app.services.agent.workflow import AgentWorkflow, STEP_PROGRESS
from app.services.domain.compliance.case_loader import import_case_folder, _json_safe, bootstrap_meeting_profile
from app.services.domain.compliance.cross_checker import build_case_facts, run_compliance_checks
from app.services.domain.compliance.finding_generator import generate_finding_narratives
from app.services.domain.compliance.classifier import classify_compliance_document
from app.services.cross_checker import check_missing_documents
from app.services.domain.registry import get_domain_pack
from app.services.meeting_service import sync_project_rollups


@dataclass
class HarnessResult:
    project_id: str
    status: str
    meeting_id: str = ""
    meeting_code: str = ""
    finding_count: int = 0
    meeting_case: Dict[str, Any] = field(default_factory=dict)
    runtime: Dict[str, Any] = field(default_factory=dict)


class ComplianceHarness:
    """会议合规观察 AI Agent Harness：案件导入 → Orchestrator → 合规规则 → Finding 交付。"""

    def __init__(
        self,
        db: Session,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ):
        self.db = db
        self.progress_callback = progress_callback
        self.trace = AgentTrace(db, "")
        self._last_pct = 0

    def _meeting(self, project_id: str, meeting_id: str) -> Meeting:
        meeting = self.db.get(Meeting, meeting_id)
        if not meeting or meeting.project_id != project_id:
            raise ValueError("meeting not found")
        return meeting

    def _meeting_files(self, project_id: str, meeting_id: str) -> List[FileRecord]:
        return self.db.query(FileRecord).filter_by(project_id=project_id, meeting_id=meeting_id).all()

    @staticmethod
    def _present_categories(files: List[FileRecord]) -> set[str]:
        return {f.document_category for f in files if f.document_category and f.document_category != "unknown"}

    @staticmethod
    def _load_compliance_rules(workflow: AgentWorkflow) -> List[dict]:
        rules = [r for r in workflow._load_rules() if str(r.get("rule_id", "")).startswith("CMP-")]
        if rules:
            return rules
        rules_path = Path(__file__).resolve().parents[4] / "rules" / "compliance_rules.json"
        return json.loads(rules_path.read_text(encoding="utf-8"))

    def _update_meeting_state(
        self,
        meeting: Meeting,
        *,
        status: Optional[str] = None,
        summary: Optional[str] = None,
        deliverable: Optional[Dict[str, Any]] = None,
        **state_updates: Any,
    ) -> Dict[str, Any]:
        state = dict(meeting.state_json or {})
        state.update(state_updates)
        meeting.state_json = state
        if status is not None:
            meeting.status = status
        if summary is not None:
            meeting.summary = summary
        if deliverable is not None:
            meeting.deliverable_json = deliverable
        return state

    def _emit_progress(self, project_id: str, meeting_id: str, step: str, pct: int | None = None) -> None:
        """同步 meeting.status、state_json.runtime_live 与 job 进度回调。"""
        pct_val = pct if pct is not None else STEP_PROGRESS.get(step, 0)
        pct_val = max(self._last_pct, pct_val)
        self._last_pct = pct_val
        now = datetime.now(timezone.utc)
        meeting = self.db.get(Meeting, meeting_id)
        project = self.db.get(Project, project_id)
        if meeting:
            self._update_meeting_state(
                meeting,
                status=step,
                runtime_live={
                "step": step,
                "pct": pct_val,
                    "updated_at": now.isoformat() + "Z",
                },
            )
            meeting.last_run_at = now
        if project:
            project.status = "active"
        if meeting or project:
            self.db.commit()
        if self.progress_callback:
            self.progress_callback(step, pct_val)

    def import_case(
        self,
        case_path: str | Path,
        project_name: Optional[str] = None,
        *,
        project_id: Optional[str] = None,
        meeting_id: Optional[str] = None,
    ) -> tuple[str, str, Dict[str, Any]]:
        pid, mid, profile = import_case_folder(
            self.db,
            Path(case_path),
            project_name,
            project_id=project_id,
            meeting_id=meeting_id,
        )
        self.trace = AgentTrace(self.db, pid, mid)
        self.trace.log(
            "harness",
            "completed",
            kind="harness",
            message=f"资料导入 {profile.get('meeting_code', '')}",
            detail={"meeting_case": profile, "meeting_id": mid},
        )
        return pid, mid, profile

    def _reclassify_files(self, project_id: str, meeting_id: str) -> None:
        files = self.db.query(FileRecord).filter_by(project_id=project_id, meeting_id=meeting_id).all()
        for f in files:
            ext = Path(f.file_name).suffix
            text_preview = ""
            path = Path(f.storage_path)
            if path.suffix.lower() == ".pdf" and path.exists():
                try:
                    from app.services.parsers.pdf_parser import parse_pdf

                    text_preview = (parse_pdf(path).get("text_content") or "")[:8000]
                except Exception:
                    pass
            elif path.suffix.lower() in (".xlsx", ".xls") and path.exists():
                try:
                    import openpyxl

                    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
                    ws = wb.active
                    rows = list(ws.iter_rows(min_row=1, max_row=8, values_only=True))
                    text_preview = "\n".join(
                        " ".join(str(c) for c in row if c is not None) for row in rows if row
                    )[:8000]
                except Exception:
                    pass
            cls = classify_compliance_document(f.file_name, ext, text_preview)
            f.document_category = cls["document_category"]
            f.file_type = cls["file_type"]
            f.confidence = cls["confidence"]
            f.meta_json = cls
        self.db.commit()

    def _run_compliance_rules(self, project_id: str, meeting_id: str) -> List[dict]:
        meeting = self._meeting(project_id, meeting_id)
        state = dict(meeting.state_json or {})
        meeting_profile = state.get("meeting_case") or bootstrap_meeting_profile(self.db, project_id, meeting_id)
        files = self._meeting_files(project_id, meeting_id)

        workflow = AgentWorkflow(self.db, project_id, self.progress_callback, meeting_id=meeting_id)
        parsed_docs = workflow._load_parsed_docs_from_db()

        facts = build_case_facts(meeting_profile, files, parsed_docs)
        rules = self._load_compliance_rules(workflow)
        hits = run_compliance_checks(facts, rules)
        obs_type = str(meeting_profile.get("observation_type") or "远程观察")
        adjudicated = generate_finding_narratives(hits, {**meeting_profile, **facts}, obs_type)

        self._update_meeting_state(
            meeting,
            meeting_case=_json_safe({**meeting_profile, **facts, "finding_count": len(adjudicated)}),
        )
        self.db.commit()

        self.trace.log(
            "harness",
            "completed",
            kind="harness",
            message=f"合规规则命中 {len(adjudicated)} 项",
            detail={"facts": facts, "hits": len(hits)},
        )
        return adjudicated

    def _persist_findings(
        self, project_id: str, meeting_id: str, findings: List[dict], files: Optional[List[FileRecord]] = None
    ) -> None:
        files = files or self._meeting_files(project_id, meeting_id)
        files_by_cat = {}
        for f in files:
            files_by_cat.setdefault(f.document_category, f.id)

        self.db.query(Risk).filter_by(project_id=project_id, meeting_id=meeting_id).delete()
        for r in findings:
            evidence = r.get("evidence_json") or {}
            source_file_id = r.get("source_file_id")
            if not source_file_id:
                for key in ("document_category", "doc_type", "category"):
                    cat = evidence.get(key)
                    if cat and cat in files_by_cat:
                        source_file_id = files_by_cat[cat]
                        break
            self.db.add(
                Risk(
                    project_id=project_id,
                    meeting_id=meeting_id,
                    risk_id=r.get("risk_id") or f"FIND-{uuid.uuid4().hex[:8]}",
                    risk_category=r["risk_category"],
                    risk_level=r["risk_level"],
                    risk_score={"高": 85, "中": 55, "低": 25}.get(r["risk_level"], 50),
                    problem=r["problem"],
                    evidence_json=evidence,
                    rule_triggered=r.get("rule_triggered"),
                    analysis=r.get("analysis"),
                    suggestion=r.get("suggestion", ""),
                    correction_action="待处理",
                    manual_review_required=r.get("manual_review_required", False),
                    confidence=r.get("confidence", 0.9),
                    status="pending",
                    source_file_id=source_file_id,
                )
            )
        self.db.commit()

    def _sync_meeting_snapshot(
        self,
        project_id: str,
        meeting_id: str,
        findings: List[dict],
        missing: list[dict],
        files: Optional[List[FileRecord]] = None,
    ) -> None:
        meeting = self._meeting(project_id, meeting_id)
        files = files or self._meeting_files(project_id, meeting_id)
        present = self._present_categories(files)
        summary = AgentWorkflow(self.db, project_id, meeting_id=meeting_id)._build_summary(
            [{"risk_level": f.get("risk_level")} for f in findings],
            missing,
        )
        self._update_meeting_state(
            meeting,
            status="completed",
            summary=summary,
            missing_documents=missing,
            present_categories=sorted(present),
            risk_count=len(findings),
            execution_mode="compliance_harness",
            agent_domain="compliance",
        )
        self.db.commit()
        sync_project_rollups(self.db, project_id)

    def _finalize_runtime_state(
        self,
        project_id: str,
        meeting_id: str,
        *,
        missing: list[dict],
        post_status: str,
    ) -> Meeting:
        meeting = self._meeting(project_id, meeting_id)
        deliverable = {"status": "pending", "comment": ""}
        self._update_meeting_state(
            meeting,
            status=post_status if post_status in ("needs_review", "completed") else "completed",
            deliverable=deliverable,
            missing_documents=missing,
        )
        self.db.commit()
        sync_project_rollups(self.db, project_id)
        return meeting

    def run(
        self,
        project_id: str,
        meeting_id: str,
        *,
        skip_orchestrator: bool = False,
    ) -> HarnessResult:
        """对单个子会议运行完整 Harness。"""
        self.trace = AgentTrace(self.db, project_id, meeting_id)
        meeting = self._meeting(project_id, meeting_id)

        pack = get_domain_pack(project=self.db.get(Project, project_id))
        self.trace.step("harness", "running", {"domain": pack.name, "project_id": project_id, "meeting_id": meeting_id})

        state = dict(meeting.state_json or {})
        if not state.get("meeting_case"):
            state["meeting_case"] = bootstrap_meeting_profile(self.db, project_id, meeting_id)
        self._update_meeting_state(
            meeting,
            status="running",
            meeting_case=state["meeting_case"],
            agent_domain="compliance",
            execution_mode="compliance_harness",
        )
        self.db.commit()

        self._emit_progress(project_id, meeting_id, "planning")
        self._reclassify_files(project_id, meeting_id)
        files = self._meeting_files(project_id, meeting_id)
        self._emit_progress(project_id, meeting_id, "classifying")

        if not skip_orchestrator:
            MissionOrchestrator(
                self.db,
                project_id,
                self.progress_callback,
                self.trace,
            ).run()

        self._emit_progress(project_id, meeting_id, "running_rules")
        findings = self._run_compliance_rules(project_id, meeting_id)
        self._emit_progress(project_id, meeting_id, "adjudicating")
        self._persist_findings(project_id, meeting_id, findings, files=files)

        present = self._present_categories(files)
        missing = check_missing_documents(present, domain="compliance")
        self._sync_meeting_snapshot(project_id, meeting_id, findings, missing, files=files)

        runtime = AgentRuntime(self.db, project_id, self.progress_callback, meeting_id=meeting_id)
        runtime.trace = self.trace
        post = runtime._post_process("full")

        meeting = self._finalize_runtime_state(
            project_id,
            meeting_id,
            missing=missing,
            post_status=post.status,
        )

        self._emit_progress(project_id, meeting_id, "completed", 100)

        meeting_case = ((meeting.state_json or {}).get("meeting_case") or {}) if meeting else {}
        return HarnessResult(
            project_id=project_id,
            meeting_id=meeting_id,
            status=post.status,
            meeting_code=str(meeting_case.get("meeting_code") or meeting.meeting_code if meeting else ""),
            finding_count=len(findings),
            meeting_case=meeting_case,
            runtime={
                "critic": post.critic_summary,
                "human_gate": post.human_gate,
            },
        )

    def run_case_folder(
        self,
        case_path: str | Path,
        project_name: Optional[str] = None,
    ) -> HarnessResult:
        project_id, meeting_id, _ = self.import_case(case_path, project_name)
        return self.run(project_id, meeting_id)
