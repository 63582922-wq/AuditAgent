from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.domain.compliance.constants import DOCUMENT_CATEGORY_LABELS
from app.services.outputs.material_layout_deliverables import _layout_summary as layout_summary_text

FONT = "STSong-Light"
LEVEL_FILLS = {
    "高": PatternFill("solid", fgColor="FFC7CE"),
    "中": PatternFill("solid", fgColor="FFEB9C"),
    "低": PatternFill("solid", fgColor="DDEBF7"),
}
HEADER_FILL = PatternFill("solid", fgColor="1E3A5F")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def _category_label(code: str) -> str:
    return DOCUMENT_CATEGORY_LABELS.get(code, code)


def _style_header(ws) -> None:
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"


def _autosize(ws, max_width: int = 48) -> None:
    for col in ws.columns:
        max_len = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, max_width)


def _evidence_summary(evidence: dict | None) -> str:
    if not evidence:
        return ""
    parts = []
    for key, val in evidence.items():
        if val in (None, "", [], {}):
            continue
        parts.append(f"{key}: {val}")
    return "；".join(parts[:6])


def generate_compliance_finding_excel(findings: list[dict], output: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Finding清单"
    headers = [
        "Finding编号",
        "等级",
        "评分",
        "类别",
        "问题描述",
        "触发规则",
        "证据摘要",
        "整改建议",
        "需人工复核",
        "状态",
    ]
    ws.append(headers)
    _style_header(ws)

    for r in sorted(findings, key=lambda x: -x.get("risk_score", 0)):
        ws.append(
            [
                r.get("risk_id"),
                r.get("risk_level"),
                r.get("risk_score"),
                r.get("risk_category"),
                r.get("problem"),
                r.get("rule_triggered"),
                _evidence_summary(r.get("evidence_json")),
                r.get("suggestion"),
                "是" if r.get("manual_review_required") else "否",
                r.get("status", "pending"),
            ]
        )
        fill = LEVEL_FILLS.get(r.get("risk_level", ""))
        if fill:
            for cell in ws[ws.max_row]:
                cell.fill = fill

    ws.auto_filter.ref = ws.dimensions
    _autosize(ws)
    wb.save(output)


def generate_missing_docs_excel(missing: list[dict], output: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "缺件清单"
    ws.append(["序号", "资料类型", "重要程度", "缺件说明", "建议补充动作"])
    _style_header(ws)

    for i, item in enumerate(missing, start=1):
        doc_type = item.get("document_type") or item.get("doc_type") or ""
        ws.append(
            [
                i,
                _category_label(str(doc_type)),
                item.get("importance", ""),
                item.get("reason", ""),
                item.get("suggestion") or "请补充对应观察证据材料并重新提交分析",
            ]
        )

    if not missing:
        ws.append(["—", "无", "—", "当前证据资料已齐套", "—"])

    ws.auto_filter.ref = ws.dimensions
    _autosize(ws)
    wb.save(output)


def generate_correction_tracking_excel(findings: list[dict], output: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "整改跟踪"
    ws.append(
        [
            "Finding编号",
            "等级",
            "问题描述",
            "整改建议",
            "整改动作",
            "优先级",
            "计划完成日",
            "责任人",
            "闭环状态",
        ]
    )
    _style_header(ws)

    priority_map = {"高": "P1", "中": "P2", "低": "P3"}
    for r in sorted(findings, key=lambda x: -x.get("risk_score", 0)):
        level = r.get("risk_level", "")
        ws.append(
            [
                r.get("risk_id"),
                level,
                r.get("problem"),
                r.get("suggestion"),
                r.get("correction_action") or "待业务确认",
                priority_map.get(level, "P2"),
                "",
                "",
                "待处理",
            ]
        )
        fill = LEVEL_FILLS.get(level, "")
        if fill:
            for cell in ws[ws.max_row]:
                cell.fill = fill

    if not findings:
        ws.append(["—", "—", "暂无 Finding", "—", "—", "—", "—", "—", "—"])

    ws.auto_filter.ref = ws.dimensions
    _autosize(ws)
    wb.save(output)


def generate_evidence_index_excel(
    findings: list[dict],
    file_names: dict[str, str],
    output: Path,
    *,
    materials_by_id: dict[str, dict] | None = None,
) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "证据索引"
    ws.append(
        [
            "Finding编号",
            "等级",
            "类别",
            "问题描述",
            "触发规则",
            "证据文件",
            "OCR 引擎",
            "版面结构",
            "OCR 摘要",
            "证据字段",
            "来源位置",
        ]
    )
    _style_header(ws)
    materials_by_id = materials_by_id or {}

    for r in findings:
        source_id = r.get("source_file_id")
        loc = r.get("source_location_json") or {}
        loc_text = ""
        if isinstance(loc, dict) and loc:
            loc_text = json.dumps(loc, ensure_ascii=False)
        mat = materials_by_id.get(str(source_id)) if source_id else None
        ocr_engine = r.get("_ocr_engine") or (mat or {}).get("ocr_engine") or ""
        layout_summary = r.get("_layout_summary") or ""
        if mat and not layout_summary:
            layout_summary = layout_summary_text(mat.get("layout_counts") or {})
        ocr_preview = r.get("_ocr_preview") or ""
        if mat and not ocr_preview:
            ocr_preview = (mat.get("text_content") or mat.get("md_results") or "")[:180].replace("\n", " ")
        ws.append(
            [
                r.get("risk_id"),
                r.get("risk_level"),
                r.get("risk_category"),
                r.get("problem"),
                r.get("rule_triggered"),
                file_names.get(source_id, "") if source_id else "",
                ocr_engine or "—",
                layout_summary or "—",
                ocr_preview or "—",
                _evidence_summary(r.get("evidence_json")),
                loc_text,
            ]
        )

    if not findings:
        ws.append(["—", "—", "—", "暂无 Finding", "—", "—", "—", "—", "—", "—", "—"])

    ws.auto_filter.ref = ws.dimensions
    _autosize(ws)
    wb.save(output)


def generate_observation_summary_pdf(
    project_name: str,
    findings: list[dict],
    missing: list[dict],
    output: Path,
    *,
    meeting_case: dict | None = None,
) -> None:
    pdfmetrics.registerFont(UnicodeCIDFont(FONT))
    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Title"], fontName=FONT, fontSize=16, textColor=colors.HexColor("#1E3A5F"))
    body = ParagraphStyle("b", parent=styles["Normal"], fontName=FONT, fontSize=10, leading=14)
    muted = ParagraphStyle("m", parent=styles["Normal"], fontName=FONT, fontSize=9, textColor=colors.grey)

    meeting_case = meeting_case or {}
    high = sum(1 for f in findings if f.get("risk_level") == "高")
    mid = sum(1 for f in findings if f.get("risk_level") == "中")
    low = sum(1 for f in findings if f.get("risk_level") == "低")
    now = datetime.now().strftime("%Y-%m-%d")

    doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm)
    story = [
        Paragraph("会议合规远程观察 · 观察摘要", title),
        Paragraph(f"Executive Summary · {project_name}", muted),
        Spacer(1, 12),
        Paragraph(
            f"会议编码：{meeting_case.get('meeting_code') or '—'}　"
            f"观察类型：{meeting_case.get('observation_type') or '远程观察'}　"
            f"生成日期：{now}",
            body,
        ),
        Spacer(1, 10),
        Paragraph(
            f"本次共识别 Finding <b>{len(findings)}</b> 项（高 {high} / 中 {mid} / 低 {low}），"
            f"缺件 {len(missing)} 类。",
            body,
        ),
        Spacer(1, 8),
        Paragraph("<b>主要结论（Top Finding）</b>", body),
    ]

    for r in findings[:5]:
        story.append(
            Paragraph(
                f"• [{r.get('risk_level', '—')}] {r.get('problem', '')}",
                body,
            )
        )

    if not findings:
        story.append(Paragraph("• 未发现需记录的 Finding。", body))

    story.append(Spacer(1, 10))
    story.append(Paragraph("<b>后续建议</b>", body))
    if missing:
        story.append(Paragraph("1. 按《缺件清单》补充观察证据资料。", body))
    story.append(Paragraph("2. 按《整改跟踪表》落实 Finding 整改并闭环。", body))
    story.append(Paragraph("3. 详述见《Remote Observation Report》与《Finding清单》。", body))

    doc.build(story)


def generate_deliverable_readme_pdf(
    project_name: str,
    output: Path,
    *,
    meeting_code: str = "",
    file_list: list[str] | None = None,
) -> None:
    pdfmetrics.registerFont(UnicodeCIDFont(FONT))
    styles = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=styles["Normal"], fontName=FONT, fontSize=10, leading=14)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm)
    story = [
        Paragraph("AuditAgent · 交付说明", ParagraphStyle("t", parent=styles["Title"], fontName=FONT, fontSize=14)),
        Spacer(1, 8),
        Paragraph(f"案件：{project_name}", body),
        Paragraph(f"会议编码：{meeting_code or '—'}", body),
        Paragraph(f"打包时间：{now}", body),
        Spacer(1, 10),
        Paragraph("本压缩包为会议合规远程观察正式交付物，包含 Finding 报告、清单、证据索引、资料视觉解析及整改跟踪文件。", body),
        Spacer(1, 8),
        Paragraph("<b>目录说明</b>", body),
    ]
    for line in file_list or []:
        story.append(Paragraph(f"• {line}", body))
    doc.build(story)


def pack_deliverable_zip(
    zip_path: Path,
    entries: dict[str, Path],
) -> None:
    """entries: archive内相对路径 -> 本地文件路径"""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, src in entries.items():
            if src.exists():
                zf.write(src, arcname)


def build_compliance_deliverable_bundle(
    out_dir: Path,
    project_name: str,
    findings: list[dict],
    missing: list[dict],
    *,
    meeting_case: dict | None = None,
    runtime: dict | None = None,
    file_names: dict[str, str] | None = None,
    parsed_materials: list[dict] | None = None,
    main_report_path: Path | None = None,
) -> dict[str, Path]:
    """生成合规商业交付物目录结构，返回 output_type -> path 映射。"""
    from app.services.outputs.compliance_pdf_report import generate_compliance_pdf_report
    from app.services.outputs.material_layout_deliverables import (
        enrich_evidence_with_layout,
        generate_material_parse_index_excel,
        material_by_file_id,
        write_material_layout_json_files,
        write_material_markdown_files,
    )

    meeting_case = meeting_case or {}
    materials = list(parsed_materials or [])
    materials_by_id = material_by_file_id(materials)
    findings_for_export = enrich_evidence_with_layout(findings, materials_by_id)
    meeting_code = str(meeting_case.get("meeting_code") or "CASE").replace("/", "-")
    date_tag = datetime.now().strftime("%Y%m%d")
    bundle_root = out_dir / f"{meeting_code}_RemoteObservation_{date_tag}"
    bundle_root.mkdir(parents=True, exist_ok=True)

    paths = {
        "report": bundle_root / "01_Finding报告" / "Remote_Observation_Report.pdf",
        "finding_excel": bundle_root / "02_Finding清单" / "Finding清单.xlsx",
        "summary": bundle_root / "03_观察摘要" / "观察摘要.pdf",
        "evidence": bundle_root / "04_证据索引" / "证据索引.xlsx",
        "missing": bundle_root / "05_缺件与整改" / "缺件清单.xlsx",
        "correction": bundle_root / "05_缺件与整改" / "整改跟踪表.xlsx",
        "material_index": bundle_root / "06_资料解析" / "资料解析索引.xlsx",
        "readme": bundle_root / "交付说明.pdf",
    }
    for p in paths.values():
        p.parent.mkdir(parents=True, exist_ok=True)

    if main_report_path and main_report_path.exists():
        paths["report"].write_bytes(main_report_path.read_bytes())
    else:
        generate_compliance_pdf_report(
            project_name,
            findings,
            missing,
            paths["report"],
            meeting_case=meeting_case,
            runtime=runtime,
            parsed_materials=materials,
        )

    generate_compliance_finding_excel(findings_for_export, paths["finding_excel"])
    generate_observation_summary_pdf(
        project_name, findings_for_export, missing, paths["summary"], meeting_case=meeting_case
    )
    generate_evidence_index_excel(
        findings_for_export, file_names or {}, paths["evidence"], materials_by_id=materials_by_id
    )
    generate_missing_docs_excel(missing, paths["missing"])
    generate_correction_tracking_excel(findings_for_export, paths["correction"])

    md_dir = paths["material_index"].parent / "markdown"
    layout_dir = paths["material_index"].parent / "layout"
    write_material_markdown_files(materials, md_dir)
    write_material_layout_json_files(materials, layout_dir)
    generate_material_parse_index_excel(materials, paths["material_index"])

    readme_files = [
        "01_Finding报告/Remote_Observation_Report.pdf",
        "02_Finding清单/Finding清单.xlsx",
        "03_观察摘要/观察摘要.pdf",
        "04_证据索引/证据索引.xlsx",
        "05_缺件与整改/缺件清单.xlsx",
        "05_缺件与整改/整改跟踪表.xlsx",
        "06_资料解析/资料解析索引.xlsx",
        "06_资料解析/markdown/（各资料 OCR Markdown）",
        "06_资料解析/layout/（各资料版面 JSON）",
    ]
    generate_deliverable_readme_pdf(
        project_name,
        paths["readme"],
        meeting_code=meeting_code,
        file_list=readme_files,
    )

    zip_path = out_dir / f"{meeting_code}_RemoteObservation_{date_tag}.zip"
    zip_entries: dict[str, Path] = {
        f"{meeting_code}_RemoteObservation_{date_tag}/{rel}": paths[key]
        for key, rel in [
            ("report", "01_Finding报告/Remote_Observation_Report.pdf"),
            ("finding_excel", "02_Finding清单/Finding清单.xlsx"),
            ("summary", "03_观察摘要/观察摘要.pdf"),
            ("evidence", "04_证据索引/证据索引.xlsx"),
            ("missing", "05_缺件与整改/缺件清单.xlsx"),
            ("correction", "05_缺件与整改/整改跟踪表.xlsx"),
            ("material_index", "06_资料解析/资料解析索引.xlsx"),
            ("readme", "交付说明.pdf"),
        ]
    }
    if md_dir.exists():
        for md_file in sorted(md_dir.glob("*.md")):
            zip_entries[f"{meeting_code}_RemoteObservation_{date_tag}/06_资料解析/markdown/{md_file.name}"] = md_file
    if layout_dir.exists():
        for json_file in sorted(layout_dir.glob("*.json")):
            zip_entries[
                f"{meeting_code}_RemoteObservation_{date_tag}/06_资料解析/layout/{json_file.name}"
            ] = json_file
    pack_deliverable_zip(zip_path, zip_entries)

    return {
        "finding_pdf": paths["report"],
        "finding_excel": paths["finding_excel"],
        "observation_summary": paths["summary"],
        "evidence_index": paths["evidence"],
        "missing_docs": paths["missing"],
        "correction_list": paths["correction"],
        "material_parse_index": paths["material_index"],
        "deliverable_readme": paths["readme"],
        "deliverable_package": zip_path,
    }


def generate_generic_missing_excel(missing: list[dict], output: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "缺件清单"
    ws.append(["序号", "资料类型", "重要程度", "缺件说明"])
    _style_header(ws)
    for i, item in enumerate(missing, start=1):
        ws.append([i, item.get("document_type"), item.get("importance"), item.get("reason")])
    if not missing:
        ws.append(["—", "无", "—", "资料已齐套"])
    _autosize(ws)
    wb.save(output)


def generate_generic_correction_excel(risks: list[dict], output: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "整改建议"
    ws.append(["序号", "风险等级", "问题描述", "整改建议", "触发规则"])
    _style_header(ws)
    for i, r in enumerate(sorted(risks, key=lambda x: -x.get("risk_score", 0)), start=1):
        ws.append([i, r.get("risk_level"), r.get("problem"), r.get("suggestion"), r.get("rule_triggered")])
    _autosize(ws)
    wb.save(output)
