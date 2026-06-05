from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AgentRunLog,
    ExtractedEntity,
    FileRecord,
    Memory,
    Output,
    ParsedDocument,
    Project,
    RecordLink,
    Risk,
    Rule,
)
from app.services.agent.llm_client import require_agent_llm
from app.services.agent.adjudicator import adjudicate_risks
from app.services.agent.planner import plan_analysis
from app.services.anomaly_detector import detect_amount_anomalies
from app.services.classifier import classify_document
from app.services.cross_checker import check_missing_documents, cross_check_amounts, detect_duplicate_invoices
from app.services.cross_period_checker import detect_cross_period_risks, detect_three_way_gaps
from app.services.entity_extractor import extract_entities_from_documents
from app.services.parsers.excel_parser import annotate_excel, parse_excel
from app.services.parsers.image_parser import annotate_image, parse_image
from app.services.parsers.pdf_parser import extract_contract_fields, parse_pdf
from app.services.parsers.word_parser import parse_word
from app.services.outputs.excel_report import generate_risk_excel
from app.services.outputs.pdf_report import generate_pdf_report
from app.services.record_linker import build_record_links, links_to_cross_risks
from app.services.risk_scorer import calculate_risk_score
from app.services.rule_engine import run_rules_on_fields, run_rules_on_rows

STEP_PROGRESS = {
    "planning": 5,
    "classifying": 10,
    "parsing": 25,
    "extracting": 40,
    "running_rules": 55,
    "cross_checking": 75,
    "adjudicating": 85,
    "generating_report": 90,
    "completed": 100,
}

RULE_CATEGORIES = (
    "expense_detail",
    "invoice_list",
    "bank_statement",
    "trial_balance",
    "accounts_payable",
    "accounts_receivable",
    "tax_return",
    "payroll",
    "social_security",
)

FIELD_RULE_CATEGORIES = ("contract", "invoice_image")


class AgentWorkflow:
    STEPS = [
        "planning",
        "classifying",
        "parsing",
        "extracting",
        "running_rules",
        "cross_checking",
        "adjudicating",
        "generating_report",
        "completed",
    ]

    def __init__(
        self,
        db: Session,
        project_id: str,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ):
        self.db = db
        self.project_id = project_id
        self.progress_callback = progress_callback

    def run(self) -> None:
        project = self.db.get(Project, self.project_id)
        if not project:
            raise ValueError("project not found")

        try:
            require_agent_llm()
            self._set_status(project, "classifying")
            self._log("classify", "running")
            files = self.db.query(FileRecord).filter_by(project_id=self.project_id).all()

            self._set_status(project, "planning")
            self._log("planning", "running")
            agent_plan = plan_analysis(self.db, self.project_id, files)
            self._log("planning", "completed", agent_plan)

            parsed_docs: list[dict] = []

            for f in files:
                ext = Path(f.file_name).suffix.lower()
                classification = classify_document(f.file_name, ext)
                f.file_type = classification["file_type"]
                f.document_category = classification["document_category"]
                f.confidence = classification["confidence"]
                f.meta_json = classification
                self.db.commit()

            self._set_status(project, "parsing")
            for f in files:
                content = self._parse_file(f)
                headers = []
                if content.get("sheets"):
                    headers = [c["name"] for c in content["sheets"][0].get("columns", [])]
                reclassify = classify_document(
                    f.file_name, Path(f.file_name).suffix, headers=headers, text=content.get("text_content", "")
                )
                if reclassify["confidence"] > (f.confidence or 0):
                    f.document_category = reclassify["document_category"]
                    f.confidence = reclassify["confidence"]
                    f.meta_json = reclassify
                pd = ParsedDocument(
                    project_id=self.project_id,
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
                    }
                )

            self._set_status(project, "extracting")
            self._progress("extracting")
            self.db.query(ExtractedEntity).filter_by(project_id=self.project_id).delete()
            self.db.query(RecordLink).filter_by(project_id=self.project_id).delete()
            entities = extract_entities_from_documents(self.project_id, parsed_docs)
            for ent in entities:
                self.db.add(
                    ExtractedEntity(
                        project_id=ent["project_id"],
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
                self.db.add(RecordLink(**link))
            self.db.commit()

            self._set_status(project, "running_rules")
            self._progress("running_rules")
            rules = self._load_rules()
            all_risks: list[dict] = []
            invoice_rows: list[dict] = []
            expense_rows: list[dict] = []

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
                            {
                                "file_id": doc["file_id"],
                                "document_category": doc["document_category"],
                            },
                        )
                        for hit in hits:
                            risk = self._hit_to_risk(hit, doc)
                            all_risks.append(risk)
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
                            all_risks.append(self._hit_to_risk(hit, doc))

                if doc["document_category"] == "expense_detail":
                    all_risks.extend(
                        detect_cross_period_risks(
                            [
                                {
                                    **r,
                                    "sheet_name": sheet["sheet_name"],
                                }
                                for sheet in doc["content_json"].get("sheets", [])
                                for r in [
                                    {
                                        "row_number": row["row_number"],
                                        "values": row["values"],
                                    }
                                    for row in sheet.get("rows", [])
                                ]
                            ],
                            doc["file_id"],
                            doc["file_name"],
                        )
                    )

            self._set_status(project, "cross_checking")
            self._progress("cross_checking")
            all_risks.extend(cross_check_amounts(parsed_docs))
            all_risks.extend(detect_duplicate_invoices(invoice_rows))
            all_risks.extend(links_to_cross_risks(links, parsed_docs))
            all_risks.extend(detect_three_way_gaps(parsed_docs, links))
            all_risks.extend(detect_amount_anomalies(expense_rows))

            present = {d["document_category"] for d in parsed_docs}
            missing = check_missing_documents(present)

            self._set_status(project, "adjudicating")
            self._progress("adjudicating")
            self._log("adjudicating", "running", {"risk_count": len(all_risks)})
            all_risks = adjudicate_risks(self.db, all_risks, agent_plan)
            for r in all_risks:
                if r.get("risk_level"):
                    scores = calculate_risk_score(
                        r["risk_level"],
                        r.get("evidence_json") or {},
                        r.get("confidence", 0.9),
                    )
                    r["risk_score"] = scores["total_score"]
                    r["risk_level"] = scores["risk_level"]
            self._log("adjudicating", "completed", {"agent_mode": agent_plan.get("agent_mode")})

            self.db.query(Risk).filter_by(project_id=self.project_id).delete()
            for r in all_risks:
                risk_obj = Risk(
                    project_id=self.project_id,
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
                self.db.add(risk_obj)
            self.db.commit()

            self._set_status(project, "generating_report")
            self._progress("generating_report")
            self._generate_outputs(project, missing)
            project.summary = self._build_summary(all_risks, missing)
            project.state_json = {
                "agent_plan": agent_plan,
                "missing_documents": missing,
                "risk_count": len(all_risks),
                "present_categories": list(present),
                "entity_count": len(entities),
                "link_count": len(links),
            }
            self._set_status(project, "completed")
            self._progress("completed")
            self._log("workflow", "completed", {"risk_count": len(all_risks)})
        except Exception as exc:
            self._set_status(project, "failed")
            self._log("workflow", "failed", {"error": str(exc)})
            raise

    def regenerate_outputs_only(self) -> None:
        """人工复核后仅重新生成交付物，不重跑分析。"""
        project = self.db.get(Project, self.project_id)
        if not project:
            raise ValueError("project not found")
        missing = (project.state_json or {}).get("missing_documents", [])
        self._set_status(project, "generating_report")
        self._generate_outputs(project, missing)
        self._set_status(project, "completed")
        self._log("regenerate_outputs", "completed", {})

    def _parse_file(self, f: FileRecord) -> dict:
        path = Path(f.storage_path)
        if f.file_type == "excel" or path.suffix.lower() in (".xlsx", ".xls", ".csv"):
            return parse_excel(path)
        if f.file_type == "pdf" or path.suffix.lower() == ".pdf":
            content = parse_pdf(path)
            if "contract" in f.document_category or "合同" in f.file_name:
                content["fields"] = extract_contract_fields(content)
                f.document_category = "contract"
            return content
        if f.file_type == "word" or path.suffix.lower() in (".docx", ".doc"):
            content = parse_word(path)
            f.document_category = "contract"
            return content
        if f.file_type == "image" or path.suffix.lower() in (".jpg", ".jpeg", ".png"):
            return parse_image(path)
        return {"file_type": "unknown", "text_content": ""}

    def _load_rules(self) -> list[dict]:
        db_rules = (
            self.db.query(Rule)
            .filter_by(enabled=True)
            .order_by(Rule.priority.desc(), Rule.rule_id)
            .all()
        )
        return [
            {
                "rule_id": r.rule_id,
                "rule_name": r.rule_name,
                "risk_category": r.risk_category,
                "risk_level": r.risk_level,
                "applicable_document_type": r.applicable_document_type,
                "condition_json": r.condition_json,
                "evidence_fields": r.evidence_fields or [],
                "suggestion_template": r.suggestion_template,
                "manual_review_required": r.manual_review_required,
                "enabled": r.enabled,
            }
            for r in db_rules
        ]

    def _hit_to_risk(self, hit: dict, doc: dict) -> dict:
        rule = hit["rule"]
        evidence = hit["evidence"]
        row_ctx = hit["row_ctx"]
        confidence = 0.9
        if doc.get("document_category") == "unknown":
            confidence = 0.6
        scores = calculate_risk_score(rule["risk_level"], evidence, confidence)
        loc_col = next((k for k in evidence if k), None)
        return {
            "risk_id": f"{rule['rule_id']}-{row_ctx.get('row_number')}",
            "risk_category": rule["risk_category"],
            "risk_subcategory": rule["rule_name"],
            "risk_level": scores["risk_level"],
            "risk_score": scores["total_score"],
            "source_file_id": doc["file_id"],
            "source_location_json": {
                "sheet": row_ctx.get("sheet_name"),
                "row": row_ctx.get("row_number"),
                "column": loc_col,
            },
            "related_files": [doc["file_name"]],
            "problem": rule["rule_name"],
            "evidence_json": evidence,
            "rule_triggered": rule["rule_id"],
            "analysis": None,
            "suggestion": rule["suggestion_template"],
            "correction_action": "标记为需补充资料" if rule["manual_review_required"] else "待核实",
            "manual_review_required": rule["manual_review_required"] or confidence < 0.75,
            "confidence": confidence,
        }

    def _generate_outputs(self, project: Project, missing: list[dict]) -> None:
        risks = (
            self.db.query(Risk)
            .filter_by(project_id=self.project_id)
            .filter(Risk.status != "dismissed")
            .all()
        )
        risk_dicts = [
            {
                "risk_id": r.risk_id,
                "risk_level": r.risk_level,
                "risk_score": r.risk_score,
                "risk_category": r.risk_category,
                "risk_subcategory": r.risk_subcategory,
                "problem": r.problem,
                "suggestion": r.suggestion,
                "evidence_json": r.evidence_json,
                "rule_triggered": r.rule_triggered,
                "manual_review_required": r.manual_review_required,
                "status": r.status,
                "source_location_json": r.source_location_json,
            }
            for r in risks
        ]

        out_dir = settings.storage_path / "outputs" / self.project_id
        out_dir.mkdir(parents=True, exist_ok=True)

        excel_path = out_dir / "风险清单.xlsx"
        generate_risk_excel(risk_dicts, excel_path)
        self._save_output(project, "risk_excel", excel_path)

        pdf_path = out_dir / "风险评估报告.pdf"
        generate_pdf_report(project.name, risk_dicts, missing, pdf_path)
        self._save_output(project, "risk_pdf", pdf_path)

        files = self.db.query(FileRecord).filter_by(project_id=self.project_id).all()
        for f in files:
            if f.file_type != "excel":
                continue
            if Path(f.file_name).suffix.lower() not in (".xlsx", ".xls", ".xlsm"):
                continue
            annotated = out_dir / f"批注_{f.file_name}"
            file_risks = [rd for rd in risk_dicts if rd.get("source_location_json")]
            annotate_excel(Path(f.storage_path), file_risks, annotated)
            self._save_output(project, "annotated_excel", annotated)

        for f in files:
            if f.file_type != "image":
                continue
            ann_path = out_dir / f"标注_{f.file_name}"
            anns = [{"bbox": None, "text": r.problem} for r in risks if r.source_file_id == f.id]
            if anns:
                annotate_image(Path(f.storage_path), anns, ann_path)
                self._save_output(project, "annotated_image", ann_path)

        suggestions_path = out_dir / "更正建议清单.json"
        suggestions_path.write_text(
            json.dumps([r.suggestion for r in risks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._save_output(project, "correction_list", suggestions_path)

        missing_path = out_dir / "补充资料清单.json"
        missing_path.write_text(json.dumps(missing, ensure_ascii=False, indent=2), encoding="utf-8")
        self._save_output(project, "missing_docs", missing_path)

    def _save_output(self, project: Project, output_type: str, path: Path) -> None:
        self.db.query(Output).filter_by(project_id=project.id, output_type=output_type).delete()
        self.db.add(
            Output(
                project_id=project.id,
                output_type=output_type,
                file_name=path.name,
                storage_path=str(path),
            )
        )
        self.db.commit()

    def _build_summary(self, risks: list[dict], missing: list[dict]) -> str:
        high = sum(1 for r in risks if r.get("risk_level") == "高")
        mid = sum(1 for r in risks if r.get("risk_level") == "中")
        low = sum(1 for r in risks if r.get("risk_level") == "低")
        return f"共识别风险 {len(risks)} 项（高 {high} / 中 {mid} / 低 {low}），缺失资料 {len(missing)} 类。"

    def _set_status(self, project: Project, status: str) -> None:
        project.status = status
        self.db.commit()
        if status in STEP_PROGRESS:
            self._progress(status)

    def _progress(self, step: str) -> None:
        pct = STEP_PROGRESS.get(step, 0)
        if self.progress_callback:
            self.progress_callback(step, pct)

    def _log(self, step: str, status: str, detail: dict | None = None) -> None:
        started = time.time()
        self.db.add(
            AgentRunLog(
                project_id=self.project_id,
                step=step,
                status=status,
                detail_json=detail,
                duration_ms=int((time.time() - started) * 1000),
            )
        )
        self.db.commit()


async def enrich_risks_with_llm(db: Session, project_id: str) -> None:
    """兼容旧调用：研判已在 workflow.adjudicating 步骤完成。"""
    return
