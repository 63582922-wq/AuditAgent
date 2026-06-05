from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def generate_pdf_report(
    project_name: str,
    risks: list[dict],
    missing: list[dict],
    output: Path,
) -> None:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"], fontName="STSong-Light")
    body_style = ParagraphStyle("body", parent=styles["Normal"], fontName="STSong-Light", fontSize=10)

    doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm)
    story = []

    story.append(Paragraph("会计风险评估报告", title_style))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"项目名称：{project_name}", body_style))
    story.append(Spacer(1, 12))

    high = sum(1 for r in risks if r.get("risk_level") == "高")
    mid = sum(1 for r in risks if r.get("risk_level") == "中")
    low = sum(1 for r in risks if r.get("risk_level") == "低")
    story.append(Paragraph(f"整体风险结论：共 {len(risks)} 项（高 {high} / 中 {mid} / 低 {low}）", body_style))
    story.append(Spacer(1, 12))

    story.append(Paragraph("一、主要高风险事项", body_style))
    for r in [x for x in risks if x.get("risk_level") == "高"][:10]:
        story.append(Paragraph(f"• {r.get('problem')} — {r.get('suggestion')}", body_style))
    story.append(Spacer(1, 12))

    story.append(Paragraph("二、详细风险清单", body_style))
    table_data = [["等级", "类别", "问题", "建议"]]
    for r in risks[:50]:
        table_data.append([
            r.get("risk_level", ""),
            r.get("risk_category", ""),
            (r.get("problem") or "")[:40],
            (r.get("suggestion") or "")[:50],
        ])
    table = Table(table_data, colWidths=[1.5 * cm, 3 * cm, 6 * cm, 6 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightblue),
                ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("三、资料缺失情况", body_style))
    for m in missing:
        story.append(Paragraph(f"• [{m.get('importance')}] {m.get('document_type')}：{m.get('reason')}", body_style))

    doc.build(story)
