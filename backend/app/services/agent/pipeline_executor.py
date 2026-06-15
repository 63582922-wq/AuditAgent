from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.models import ExtractedEntity, FileRecord, ParsedDocument, Project, RecordLink, Risk
from app.services.agent.adjudicator import adjudicate_risks
from app.services.agent.agent_trace import AgentTrace
from app.services.agent.execution_graph import ExecutionGraph
from app.services.agent.planner import plan_analysis
from app.services.agent.workflow import (
    FIELD_RULE_CATEGORIES,
    RULE_CATEGORIES,
    AgentWorkflow,
)
from app.services.anomaly_detector import detect_amount_anomalies
from app.services.agent.domain_classify import classify_uploaded_file
from app.services.agent.modality_router import is_vision_file
from app.services.parsers.parsed_doc_entries import flatten_parsed_docs
from app.services.cross_checker import check_missing_documents, cross_check_amounts, detect_duplicate_invoices
from app.services.cross_period_checker import detect_cross_period_risks, detect_three_way_gaps
from app.services.entity_extractor import extract_entities_from_documents
from app.services.record_linker import build_record_links, links_to_cross_risks
from app.services.risk_scorer import calculate_risk_score
import uuid

from app.services.rule_engine import run_rules_on_fields, run_rules_on_rows


from app.services.agent.meeting_scope import scoped_delete, scoped_query


class PipelineExecutor:
    """内环步骤执行器，供 ReAct 外环逐步调度。"""

    EXECUTABLE_STEPS = frozenset(
        {
            "classifying",
            "vision_parsing",
            "parsing",
            "extracting",
            "running_rules",
            "cross_checking",
            "adjudicating",
            "generating_report",
        }
    )

    def __init__(
        self,
        db: Session,
        project_id: str,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        trace: Optional[AgentTrace] = None,
        meeting_id: Optional[str] = None,
    ):
        self.db = db
        self.project_id = project_id
        self.meeting_id = meeting_id
        self.progress_callback = progress_callback
        self.trace = trace or AgentTrace(db, project_id, meeting_id)
        self.wf = AgentWorkflow(db, project_id, progress_callback, meeting_id=meeting_id)
        self.state: Dict[str, Any] = {
            "completed_steps": set(),
            "agent_plan": {},
            "graph": None,
            "files": [],
            "parsed_docs": [],
            "links": [],
            "entities": [],
            "all_risks": [],
            "invoice_rows": [],
            "expense_rows": [],
            "missing": [],
            "present": set(),
            "file_count": 0,
        }

    @property
    def project(self) -> Project:
        p = self.db.get(Project, self.project_id)
        if not p:
            raise ValueError("project not found")
        return p

    def bootstrap_planning(self) -> None:
        files = scoped_query(self.db, FileRecord, self.project_id, self.meeting_id).all()
        agent_plan = plan_analysis(self.db, self.project_id, files)
        graph = ExecutionGraph.from_plan(agent_plan, files)
        self.trace.plan(agent_plan, graph.to_dict())
        self.state.update(
            {
                "agent_plan": agent_plan,
                "graph": graph,
                "files": files,
                "file_count": len(files),
                "parsed_docs": [],
                "links": [],
                "entities": [],
                "all_risks": [],
                "invoice_rows": [],
                "expense_rows": [],
            }
        )

    def get_observation(self) -> Dict[str, Any]:
        graph: ExecutionGraph | None = self.state.get("graph")
        plan = self.state.get("agent_plan") or {}
        return {
            "completed_steps": sorted(self.state.get("completed_steps") or []),
            "file_count": self.state.get("file_count", 0),
            "parsed_count": len(self.state.get("parsed_docs") or []),
            "risk_count": len(self.state.get("all_risks") or []),
            "entity_count": len(self.state.get("entities") or []),
            "link_count": len(self.state.get("links") or []),
            "focus_areas": plan.get("focus_areas") or [],
            "sub_agents": [sa.get("name") for sa in plan.get("sub_agents") or []],
            "plan_steps": (graph.to_dict().get("plan_steps") if graph else []),
            "present_categories": sorted(self.state.get("present") or []),
        }

    def execute_step(self, step: str) -> Dict[str, Any]:
        if step not in self.EXECUTABLE_STEPS:
            raise ValueError(f"unsupported step: {step}")

        graph: ExecutionGraph = self.state["graph"]
        project = self.project
        files: List[FileRecord] = self.state["files"]

        if step == "classifying":
            self.wf._set_status(project, "classifying")
            for f in files:
                ext = Path(f.file_name).suffix.lower()
                classification = classify_uploaded_file(f.file_name, ext)
                f.file_type = classification["file_type"]
                f.document_category = classification["document_category"]
                f.confidence = classification["confidence"]
                f.meta_json = classification
                self.db.commit()
            self.state["graph"] = ExecutionGraph.from_plan(self.state["agent_plan"], files)
            self.state["completed_steps"].add(step)
            return {"step": step, "file_count": len(files)}

        if step == "vision_parsing":
            from app.services.agent.vision_agent_runner import VisionAgentRunner

            self.wf._set_status(project, "vision_parsing")
            count = VisionAgentRunner.parse_vision_files(self, self.trace)
            self.state["graph"] = ExecutionGraph.from_plan(self.state["agent_plan"], files)
            self.state["completed_steps"].add(step)
            return {"step": step, "vision_parsed": count}

        if step == "parsing":
            parsed_docs: List[dict] = list(self.state.get("parsed_docs") or [])
            self.wf._set_status(project, "parsing")
            for f in files:
                if is_vision_file(f):
                    continue
                content = self.wf._parse_file(f)
                headers = []
                if content.get("sheets"):
                    headers = [c["name"] for c in content["sheets"][0].get("columns", [])]
                reclassify = classify_uploaded_file(
                    f.file_name, Path(f.file_name).suffix, headers=headers, text=content.get("text_content", "")
                )
                if reclassify["confidence"] > (f.confidence or 0):
                    f.document_category = reclassify["document_category"]
                    f.confidence = reclassify["confidence"]
                    f.meta_json = reclassify
                pd = ParsedDocument(
                    project_id=self.project_id,
                    meeting_id=self.meeting_id,
                    file_id=f.id,
                    document_type=f.document_category,
                    content_json=content,
                    text_content=content.get("text_content", ""),
                )
                self.db.merge(pd)
                f.parse_status = "done"
                self.db.commit()
                parsed_docs.append(
                    {
                        "file_id": f.id,
                        "file_name": f.file_name,
                        "document_category": f.document_category,
                        "content_json": content,
                        "text_content": content.get("text_content", ""),
                    }
                )
            parsed_docs = flatten_parsed_docs(parsed_docs)
            self.state["parsed_docs"] = parsed_docs
            self.state["graph"] = ExecutionGraph.from_plan(self.state["agent_plan"], files)
            self.state["completed_steps"].add(step)
            return {"step": step, "parsed": len(parsed_docs)}

        if step == "extracting":
            parsed_docs = self.state["parsed_docs"]
            self.wf._set_status(project, "extracting")
            self.wf._progress("extracting")
            self.db.query(ExtractedEntity).filter_by(
                project_id=self.project_id, meeting_id=self.meeting_id
            ).delete()
            self.db.query(RecordLink).filter_by(
                project_id=self.project_id, meeting_id=self.meeting_id
            ).delete()
            entities = extract_entities_from_documents(self.project_id, parsed_docs)
            for ent in entities:
                self.db.add(
                    ExtractedEntity(
                        project_id=ent["project_id"],
                        meeting_id=self.meeting_id,
                        file_id=ent["file_id"],
                        entity_type=ent["entity_type"],
                        entity_value=ent["entity_value"],
                        standard_value=ent.get("standard_value"),
                        source_location=ent.get("source_location"),
                        confidence=ent.get("confidence"),
                    )
                )
            links = build_record_links(self.project_id, entities)
            for link in links:
                payload = {**link, "meeting_id": self.meeting_id}
                self.db.add(RecordLink(**payload))
            self.db.commit()
            self.state["entities"] = entities
            self.state["links"] = links
            self.state["completed_steps"].add(step)
            return {"step": step, "entities": len(entities), "links": len(links)}

        if step == "running_rules":
            parsed_docs = self.state["parsed_docs"]
            graph = self.state["graph"]
            all_risks: List[dict] = []
            invoice_rows: List[dict] = []
            expense_rows: List[dict] = []
            self.wf._set_status(project, "running_rules")
            self.wf._progress("running_rules")
            rules = graph.sort_rules(self.wf._load_rules())
            for doc in parsed_docs:
                if doc["document_category"] in RULE_CATEGORIES:
                    for sheet in doc["content_json"].get("sheets", []):
                        columns_map = {
                            c["name"]: c.get("standard_field")
                            for c in sheet.get("columns", [])
                            if c.get("standard_field")
                        }
                        rows = [
                            {
                                "row_number": r["row_number"],
                                "values": r["values"],
                                "columns_map": columns_map,
                                "sheet_name": sheet["sheet_name"],
                            }
                            for r in sheet.get("rows", [])
                        ]
                        hits = run_rules_on_rows(
                            rows,
                            rules,
                            {"file_id": doc["file_id"], "document_category": doc["document_category"]},
                        )
                        for hit in hits:
                            all_risks.append(self.wf._hit_to_risk(hit, doc))
                        if doc["document_category"] == "expense_detail":
                            expense_rows.extend(rows)
                        if doc["document_category"] in ("expense_detail", "invoice_list"):
                            for r in rows:
                                vals = r["values"]
                                inv = vals.get("invoice_number") or vals.get("发票号") or vals.get("发票号码")
                                if inv:
                                    invoice_rows.append(
                                        {
                                            "invoice_number": str(inv),
                                            "row": r["row_number"],
                                            "file_name": doc["file_name"],
                                        }
                                    )
                if doc["document_category"] in FIELD_RULE_CATEGORIES:
                    fields = doc["content_json"].get("fields") or {}
                    if fields:
                        hits = run_rules_on_fields(
                            fields,
                            rules,
                            {"file_id": doc["file_id"], "document_category": doc["document_category"]},
                        )
                        for hit in hits:
                            all_risks.append(self.wf._hit_to_risk(hit, doc))
                if doc["document_category"] == "expense_detail" and graph.should_run_cross("cross_period"):
                    all_risks.extend(
                        detect_cross_period_risks(
                            [
                                {**r, "sheet_name": sheet["sheet_name"]}
                                for sheet in doc["content_json"].get("sheets", [])
                                for r in [
                                    {"row_number": row["row_number"], "values": row["values"]}
                                    for row in sheet.get("rows", [])
                                ]
                            ],
                            doc["file_id"],
                            doc["file_name"],
                        )
                    )
            self.state["all_risks"] = all_risks
            self.state["invoice_rows"] = invoice_rows
            self.state["expense_rows"] = expense_rows
            self.state["completed_steps"].add(step)
            return {"step": step, "rule_hits": len(all_risks)}

        if step == "cross_checking":
            parsed_docs = self.state["parsed_docs"]
            graph = self.state["graph"]
            all_risks = list(self.state["all_risks"])
            self.wf._set_status(project, "cross_checking")
            self.wf._progress("cross_checking")
            if graph.should_run_cross("amounts"):
                all_risks.extend(cross_check_amounts(parsed_docs))
            if graph.should_run_cross("duplicates"):
                all_risks.extend(detect_duplicate_invoices(self.state["invoice_rows"]))
            if graph.should_run_cross("record_links"):
                all_risks.extend(links_to_cross_risks(self.state["links"], parsed_docs))
            if graph.should_run_cross("three_way"):
                all_risks.extend(detect_three_way_gaps(parsed_docs, self.state["links"]))
            if graph.should_run_cross("anomalies"):
                all_risks.extend(detect_amount_anomalies(self.state["expense_rows"]))
            self.state["all_risks"] = all_risks
            self.state["completed_steps"].add(step)
            return {"step": step, "total_risks": len(all_risks)}

        if step == "adjudicating":
            all_risks = list(self.state["all_risks"])
            self.wf._set_status(project, "adjudicating")
            self.wf._progress("adjudicating")
            all_risks = adjudicate_risks(self.db, all_risks, self.state["agent_plan"])
            for r in all_risks:
                if r.get("risk_level"):
                    scores = calculate_risk_score(
                        r["risk_level"],
                        r.get("evidence_json") or {},
                        r.get("confidence", 0.9),
                    )
                    r["risk_score"] = scores["total_score"]
                    r["risk_level"] = scores["risk_level"]
            self.state["all_risks"] = all_risks
            self.state["completed_steps"].add(step)
            return {"step": step, "risk_count": len(all_risks)}

        if step == "generating_report":
            parsed_docs = self.state["parsed_docs"]
            all_risks = self.state["all_risks"]
            present = {d["document_category"] for d in parsed_docs}
            missing = check_missing_documents(present)
            self.state["present"] = present
            self.state["missing"] = missing

            scoped_delete(self.db, Risk, self.project_id, self.meeting_id)
            for r in all_risks:
                self.db.add(
                    Risk(
                        project_id=self.project_id,
                        meeting_id=self.meeting_id,
                        risk_id=r.get("risk_id") or f"RISK-{uuid.uuid4().hex[:8]}",
                        risk_category=r["risk_category"],
                        risk_subcategory=r.get("risk_subcategory"),
                        risk_level=r["risk_level"],
                        risk_score=r.get("risk_score", 0),
                        source_file_id=r.get("source_file_id"),
                        source_location_json=r.get("source_location_json"),
                        related_files=r.get("related_files"),
                        problem=r["problem"],
                        evidence_json=r["evidence_json"],
                        rule_triggered=r.get("rule_triggered"),
                        analysis=r.get("analysis"),
                        suggestion=r["suggestion"],
                        correction_action=r.get("correction_action", "待处理"),
                        manual_review_required=r.get("manual_review_required", False),
                        confidence=r.get("confidence", 0.9),
                        status="pending",
                    )
                )
            self.db.commit()

            self.wf._set_status(project, "generating_report")
            self.wf._progress("generating_report")
            self.wf._generate_outputs(project, missing)
            self.state["completed_steps"].add(step)
            return {"step": step, "outputs": True}

        return {"step": step, "skipped": True}

    def finalize(
        self,
        execution_mode: str = "react",
        mission: Optional[Dict[str, Any]] = None,
    ) -> None:
        completed: Set[str] = self.state.get("completed_steps") or set()
        if "generating_report" not in completed and self.state.get("all_risks"):
            if "adjudicating" not in completed and "running_rules" in completed:
                self.execute_step("adjudicating")
            self.execute_step("generating_report")

        project = self.project
        graph: ExecutionGraph = self.state["graph"]
        all_risks = self.state["all_risks"]
        missing = self.state.get("missing") or []
        files = self.state["files"]
        entities = self.state.get("entities") or []
        links = self.state.get("links") or []
        present = self.state.get("present") or set()

        if not missing and self.state.get("parsed_docs"):
            present = {d["document_category"] for d in self.state["parsed_docs"]}
            missing = check_missing_documents(present)

        project.summary = self.wf._build_summary(all_risks, missing)
        prior = dict(project.state_json or {})
        state_json: Dict[str, Any] = {
            **prior,
            "agent_plan": self.state["agent_plan"],
            "execution_graph": graph.to_dict(),
            "missing_documents": missing,
            "risk_count": len(all_risks),
            "present_categories": list(present),
            "entity_count": len(entities),
            "link_count": len(links),
            "processed_file_ids": [f.id for f in files],
            "execution_mode": execution_mode,
            "completed_steps": sorted(self.state.get("completed_steps") or []),
            "deliverable": prior.get("deliverable") or {"status": "pending", "comment": ""},
        }
        if mission:
            state_json["mission"] = mission
        briefs = self.state.get("sub_agent_briefs")
        if briefs:
            state_json["sub_agent_briefs"] = briefs
        synthesis = self.state.get("synthesis_brief")
        if synthesis:
            state_json["synthesis_brief"] = synthesis
        if execution_mode == "react":
            state_json["react_completed_steps"] = state_json["completed_steps"]
        project.state_json = state_json
        self.wf._set_status(project, "completed")
        self.wf._progress("completed")
        self.trace.step("workflow", "completed", {"risk_count": len(all_risks), "mode": execution_mode})

    def run_react(self) -> Dict[str, Any]:
        from app.services.agent.react_loop import run_react_loop

        self.bootstrap_planning()
        result = run_react_loop(self, self.trace)
        self.finalize()
        return result
