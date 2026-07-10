from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import CaseRun, FileRecord, Meeting, ParsedDocument, Project, Risk
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
from app.services.evaluation.compliance_eval import (
    compact_compliance_evaluation,
    run_db_compliance_evaluation,
)
from app.services.meeting_service import sync_project_rollups
from app.services.parsed_document_store import upsert_parsed_document
from app.services.agent.case_run import create_case_run, finish_case_run, mark_case_run_started
from app.services.domain.compliance.evidence_graph import (
    apply_fact_decisions,
    evidence_gate,
    materialize_evidence_graph,
)


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
        self.run_id: str | None = None

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
            next_status = step
            if step == "completed":
                deliverable = dict(meeting.deliverable_json or (meeting.state_json or {}).get("deliverable") or {})
                gate = deliverable.get("evaluation_gate") if isinstance(deliverable.get("evaluation_gate"), dict) else {}
                if meeting.status == "needs_review" or deliverable.get("status") == "needs_review" or gate.get("blocked"):
                    next_status = "needs_review"
            self._update_meeting_state(
                meeting,
                status=next_status,
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
        if self.run_id:
            decisions = materialize_evidence_graph(
                self.db,
                run_id=self.run_id,
                project_id=project_id,
                meeting_id=meeting_id,
                facts=facts,
            )
            facts = apply_fact_decisions(facts, decisions)
            state["evidence_gate"] = evidence_gate(decisions, self._present_categories(files))
            self.trace.log(
                "evidence_graph",
                "completed",
                kind="evidence",
                name="事实证据账本",
                message=f"已裁决 {len(decisions)} 项事实，冲突 {sum(1 for item in decisions if item.status == 'conflict')} 项",
                detail={
                    "decision_count": len(decisions),
                    "accepted_count": sum(1 for item in decisions if item.status == "accepted"),
                    "conflict_count": sum(1 for item in decisions if item.status == "conflict"),
                    "needs_review_count": sum(1 for item in decisions if item.status == "needs_review"),
                    "evidence_gate": state["evidence_gate"],
                },
            )
        rules = self._load_compliance_rules(workflow)
        hits, rule_outcomes = run_compliance_checks(facts, rules, return_outcomes=True)
        obs_type = str(meeting_profile.get("observation_type") or "远程观察")
        adjudicated = generate_finding_narratives(hits, {**meeting_profile, **facts}, obs_type)

        self._update_meeting_state(
            meeting,
            meeting_case=_json_safe({**meeting_profile, **facts, "finding_count": len(adjudicated)}),
            evidence_gate=state.get("evidence_gate"),
            rule_outcomes=_json_safe(rule_outcomes),
        )
        self.db.commit()

        self.trace.log(
            "harness",
            "completed",
            kind="harness",
            message=f"合规规则命中 {len(adjudicated)} 项",
            detail={
                "facts": facts,
                "hits": len(hits),
                "evidence_gate": state.get("evidence_gate"),
                "rule_outcome_counts": {
                    status: sum(1 for item in rule_outcomes if item.get("status") == status)
                    for status in ("passed", "finding", "needs_review", "not_applicable")
                },
            },
        )
        self.trace.log(
            "rule_outcomes",
            "completed",
            kind="validation",
            name="CMP 规则裁决",
            message="规则结果已写入审核结论",
            detail={
                "rule_outcome_counts": {
                    status: sum(1 for item in rule_outcomes if item.get("status") == status)
                    for status in ("passed", "finding", "needs_review", "not_applicable")
                },
                "evidence_gate": state.get("evidence_gate"),
            },
        )
        return adjudicated

    def _ensure_parsed_documents(self, project_id: str, meeting_id: str) -> int:
        """保证规则/交付前至少完成基础资料解析；用于跳过 Orchestrator 或 Orchestrator 漏解析的场景。"""
        workflow = AgentWorkflow(self.db, project_id, self.progress_callback, meeting_id=meeting_id)
        existing_ids = {
            row[0]
            for row in self.db.query(ParsedDocument.file_id)
            .filter_by(project_id=project_id, meeting_id=meeting_id)
            .all()
        }
        parsed_count = 0
        for f in self._meeting_files(project_id, meeting_id):
            if f.id in existing_ids:
                continue
            suffix = Path(f.storage_path or f.file_name).suffix.lower()
            if suffix not in (".xlsx", ".xls", ".csv", ".docx", ".doc"):
                self.trace.log(
                    "parsing",
                    "skipped",
                    kind="tool",
                    message=f"跳过同步兜底解析 {f.file_name}",
                    detail={"file_id": f.id, "reason": "vision_or_pdf_pipeline"},
                )
                continue
            try:
                content = workflow._parse_file(f)
                upsert_parsed_document(
                    self.db,
                    project_id=project_id,
                    meeting_id=meeting_id,
                    file_id=f.id,
                    document_type=f.document_category,
                    content_json=content,
                    text_content=content.get("text_content", ""),
                )
                f.parse_status = "done"
                parsed_count += 1
                self.trace.log(
                    "parsing",
                    "completed",
                    kind="tool",
                    message=f"解析资料 {f.file_name}",
                    detail={"file_id": f.id, "document_category": f.document_category},
                )
            except Exception as exc:
                f.parse_status = "failed"
                self.trace.log(
                    "parsing",
                    "failed",
                    kind="tool",
                    message=f"解析资料失败 {f.file_name}: {exc}",
                    detail={"file_id": f.id, "error": str(exc)},
                )
        self.db.commit()
        return parsed_count

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
        state = dict(meeting.state_json or {})
        deliverable = dict(meeting.deliverable_json or state.get("deliverable") or {})
        deliverable.setdefault("status", "pending")
        deliverable.setdefault("comment", "")
        self._update_meeting_state(
            meeting,
            status=post_status if post_status in ("needs_review", "completed") else "completed",
            deliverable=deliverable,
            missing_documents=missing,
        )
        self.db.commit()
        sync_project_rollups(self.db, project_id)
        return meeting

    def _persist_evaluation(self, project_id: str, meeting_id: str) -> dict[str, Any]:
        report = run_db_compliance_evaluation(self.db, project_id, meeting_id)
        meeting = self._meeting(project_id, meeting_id)
        state = dict(meeting.state_json or {})
        state["evaluation"] = report

        deliverable = dict(meeting.deliverable_json or state.get("deliverable") or {})
        deliverable.setdefault("status", "pending")
        deliverable.setdefault("comment", "")
        deliverable["evaluation"] = compact_compliance_evaluation(report)
        evidence_state = state.get("evidence_gate") if isinstance(state.get("evidence_gate"), dict) else {}
        if evidence_state.get("blocked"):
            deliverable["status"] = "needs_review"
            deliverable["evidence_gate"] = evidence_state
            deliverable["comment"] = "关键事实存在冲突或缺少直接证据，当前仅生成待复核预览交付物。"
            meeting.status = "needs_review"
        if (
            report.get("status") == "completed"
            and report.get("passed") is False
            and int(report.get("critical_failures") or 0) > 0
        ):
            failed_ids = [
                str(item.get("check_id"))
                for item in report.get("checks", [])
                if not item.get("passed") and item.get("severity") == "critical" and item.get("check_id")
            ]
            deliverable["status"] = "needs_review"
            deliverable["evaluation_gate"] = {
                "blocked": True,
                "reason": "automatic_evaluation_failed",
                "critical_failures": int(report.get("critical_failures") or 0),
                "failed_check_ids": failed_ids,
            }
            deliverable["comment"] = "自动评估存在严重失败，需定向复核后再交付。"
            meeting.status = "needs_review"
        elif report.get("status") == "completed" and report.get("passed") is True:
            deliverable["evaluation_gate"] = {
                "blocked": False,
                "reason": "automatic_evaluation_passed",
                "critical_failures": 0,
                "failed_check_ids": [],
            }
        state["deliverable"] = deliverable
        meeting.state_json = state
        meeting.deliverable_json = deliverable
        self.db.commit()

        if report.get("status") == "skipped":
            self.trace.log(
                "compliance_evaluation",
                "skipped",
                kind="evaluation",
                message="未命中评估基准，跳过自动评分",
                detail={"meeting_code": report.get("meeting_code"), "reason": report.get("reason")},
            )
        else:
            self.trace.log(
                "compliance_evaluation",
                "completed" if report.get("passed") else "failed",
                kind="evaluation",
                message=(
                    f"自动评估 {'通过' if report.get('passed') else '未通过'}："
                    f"{report.get('passed_checks', 0)}/{report.get('total_checks', 0)} 项"
                ),
                detail={
                    "case_id": report.get("case_id"),
                    "critical_failures": report.get("critical_failures", 0),
                    "warning_failures": report.get("warning_failures", 0),
                },
            )
        return report

    def run(
        self,
        project_id: str,
        meeting_id: str,
        *,
        skip_orchestrator: bool = False,
        case_run_id: str | None = None,
    ) -> HarnessResult:
        """对单个子会议运行完整 Harness。"""
        case_run = self.db.get(CaseRun, case_run_id) if case_run_id else None
        if not case_run:
            case_run = create_case_run(
                self.db,
                project_id,
                meeting_id,
                execution_mode="compliance_harness",
            )
        self.run_id = case_run.id
        mark_case_run_started(self.db, case_run)
        self.trace = AgentTrace(self.db, project_id, meeting_id, run_id=case_run.id)
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
            active_run_id=case_run.id,
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
                meeting_id,
            ).run()

        self._emit_progress(project_id, meeting_id, "parsing")
        self._ensure_parsed_documents(project_id, meeting_id)

        self._emit_progress(project_id, meeting_id, "running_rules")
        findings = self._run_compliance_rules(project_id, meeting_id)
        self._emit_progress(project_id, meeting_id, "adjudicating")
        self._persist_findings(project_id, meeting_id, findings, files=files)

        present = self._present_categories(files)
        meeting_case = dict((meeting.state_json or {}).get("meeting_case") or {})
        missing = check_missing_documents(present, domain="compliance", meeting_case=meeting_case)
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
        self._persist_evaluation(project_id, meeting_id)

        self._emit_progress(project_id, meeting_id, "completed", 100)

        meeting = self._meeting(project_id, meeting_id)
        meeting_case = ((meeting.state_json or {}).get("meeting_case") or {}) if meeting else {}
        final_status = meeting.status if meeting else post.status
        finish_case_run(
            self.db,
            case_run,
            status=final_status,
            result={
                "meeting_code": meeting_case.get("meeting_code"),
                "finding_count": len(findings),
                "evidence_gate": (meeting.state_json or {}).get("evidence_gate") if meeting else {},
                "deliverable": meeting.deliverable_json if meeting else {},
            },
        )
        return HarnessResult(
            project_id=project_id,
            meeting_id=meeting_id,
            status=final_status,
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
