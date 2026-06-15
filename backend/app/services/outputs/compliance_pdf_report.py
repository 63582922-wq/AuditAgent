from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

FONT = "STSong-Light"
PAGE_W, PAGE_H = A4

_SECTIONS = "一二三四五六七八九十"


def _section_num(n: int) -> str:
    if 1 <= n <= len(_SECTIONS):
        return _SECTIONS[n - 1]
    return str(n)


LEVEL_COLORS = {
    "高": colors.HexColor("#E06C88"),
    "中": colors.HexColor("#E8B84A"),
    "低": colors.HexColor("#5EB8D4"),
}
LEVEL_BG = {
    "高": colors.HexColor("#3D1F28"),
    "中": colors.HexColor("#3D3218"),
    "低": colors.HexColor("#1A2E38"),
}


class ChartFlowable(Flowable):
    """ReportLab Drawing 包装为 Flowable。"""

    def __init__(self, drawing: Drawing, width: float, height: float):
        super().__init__()
        self.drawing = drawing
        self.width = width
        self.height = height

    def draw(self) -> None:
        self.drawing.drawOn(self.canv, 0, 0)


def _styles() -> dict[str, ParagraphStyle]:
    pdfmetrics.registerFont(UnicodeCIDFont(FONT))
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontName=FONT,
            fontSize=22,
            leading=28,
            textColor=colors.HexColor("#5EB8D4"),
            alignment=TA_LEFT,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=11,
            textColor=colors.HexColor("#94A3B8"),
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName=FONT,
            fontSize=14,
            textColor=colors.HexColor("#5EB8D4"),
            spaceBefore=14,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName=FONT,
            fontSize=11,
            textColor=colors.white,
            spaceBefore=6,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=9,
            leading=14,
            textColor=colors.HexColor("#E2E8F0"),
        ),
        "muted": ParagraphStyle(
            "muted",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=8,
            textColor=colors.HexColor("#94A3B8"),
        ),
        "card_title": ParagraphStyle(
            "card_title",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=10,
            leading=14,
            textColor=colors.white,
        ),
        "badge": ParagraphStyle(
            "badge",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=8,
            alignment=TA_CENTER,
            textColor=colors.white,
        ),
    }


def _level_bar_chart(findings: list[dict], width: float = 14 * cm, height: float = 5.5 * cm) -> ChartFlowable:
    counts = {"高": 0, "中": 0, "低": 0}
    for f in findings:
        lvl = f.get("risk_level") or "中"
        if lvl in counts:
            counts[lvl] += 1

    data = [[counts["高"], counts["中"], counts["低"]]]
    drawing = Drawing(width, height)
    bc = VerticalBarChart()
    bc.x = 40
    bc.y = 30
    bc.height = height - 50
    bc.width = width - 70
    bc.data = data
    bc.categoryAxis.categoryNames = ["High", "Mid", "Low"]
    bc.categoryAxis.labels.fontSize = 8
    bc.valueAxis.valueMin = 0
    bc.valueAxis.labels.fontSize = 7
    bc.bars[(0, 0)].fillColor = LEVEL_COLORS["高"]
    bc.bars[(0, 1)].fillColor = LEVEL_COLORS["中"]
    bc.bars[(0, 2)].fillColor = LEVEL_COLORS["低"]
    bc.barWidth = 18
    drawing.add(bc)
    return ChartFlowable(drawing, width, height)


def _pipeline_drawing(width: float = 16 * cm, height: float = 2.2 * cm) -> ChartFlowable:
    steps = ["UPLOAD", "CMD", "READ", "RULES", "FIND", "CRITIC", "OUT"]
    drawing = Drawing(width, height)
    drawing.add(Rect(0, 0, width, height, fillColor=colors.HexColor("#12151C"), strokeColor=colors.HexColor("#2A3344")))
    n = len(steps)
    gap = (width - 40) / (n - 1)
    y = height / 2
    for i, label in enumerate(steps):
        x = 20 + i * gap
        fill = colors.HexColor("#5EB8D4") if i >= n - 2 else colors.HexColor("#1E293B")
        stroke = colors.HexColor("#5EB8D4")
        drawing.add(Rect(x - 14, y - 10, 28, 20, fillColor=fill, strokeColor=stroke, strokeWidth=0.8, rx=3, ry=3))
        drawing.add(String(x - 12, y - 4, label, fontSize=6, fillColor=colors.white))
        if i < n - 1:
            nx = 20 + (i + 1) * gap
            drawing.add(Line(x + 16, y, nx - 16, y, strokeColor=colors.HexColor("#5EB8D4"), strokeWidth=1))
    return ChartFlowable(drawing, width, height)


def _metric_row(findings: list[dict], styles: dict[str, ParagraphStyle]) -> Table:
    high = sum(1 for f in findings if f.get("risk_level") == "高")
    mid = sum(1 for f in findings if f.get("risk_level") == "中")
    low = sum(1 for f in findings if f.get("risk_level") == "低")
    manual = sum(1 for f in findings if f.get("manual_review_required"))
    cells = [
        _metric_cell("Finding 总数", str(len(findings)), styles),
        _metric_cell("高", str(high), styles, LEVEL_COLORS["高"]),
        _metric_cell("中", str(mid), styles, LEVEL_COLORS["中"]),
        _metric_cell("低", str(low), styles, LEVEL_COLORS["低"]),
        _metric_cell("需人工复核", str(manual), styles, colors.HexColor("#A78BFA")),
    ]
    t = Table([cells], colWidths=[3.2 * cm] * 5)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _metric_cell(label: str, value: str, styles: dict[str, ParagraphStyle], accent: colors.Color | None = None) -> Table:
    accent = accent or colors.HexColor("#5EB8D4")
    inner = Table(
        [
            [Paragraph(f'<font color="#94A3B8">{label}</font>', styles["muted"])],
            [Paragraph(f'<font color="{accent.hexval()}"><b>{value}</b></font>', styles["h2"])],
        ],
        colWidths=[2.8 * cm],
    )
    inner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#12151C")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#2A3344")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return inner


def _meeting_info_table(meeting_case: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table | None:
    if not meeting_case:
        return None
    fields = [
        ("会议编码", meeting_case.get("meeting_code")),
        ("观察类型", meeting_case.get("observation_type")),
        ("会议类型", meeting_case.get("meeting_type")),
        ("BU", meeting_case.get("bu")),
        ("申请人", meeting_case.get("applicant")),
        ("计划时长(分)", meeting_case.get("planned_duration_minutes")),
        ("实际时长(分)", meeting_case.get("actual_duration_minutes")),
        ("讲者时长(分)", meeting_case.get("speaker_service_minutes")),
        ("计划参会", meeting_case.get("planned_attendees")),
        ("实际签到", meeting_case.get("actual_sign_in_count")),
        ("观察成功", meeting_case.get("observation_success")),
    ]
    rows = [[Paragraph(f"<b>{k}</b>", styles["body"]), Paragraph(str(v or "—"), styles["body"])] for k, v in fields if v is not None]
    if not rows:
        return None
    t = Table(rows, colWidths=[4 * cm, 11 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#12151C")),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#12151C"), colors.HexColor("#0F1218")]),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#2A3344")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#1E293B")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


def _material_vision_table(
    materials: list[dict],
    styles: dict[str, ParagraphStyle],
) -> Table | None:
    if not materials:
        return None
    from app.services.outputs.material_layout_deliverables import _layout_summary

    header = [
        Paragraph("<b>文件名</b>", styles["body"]),
        Paragraph("<b>资料类型</b>", styles["body"]),
        Paragraph("<b>OCR 引擎</b>", styles["body"]),
        Paragraph("<b>版面结构</b>", styles["body"]),
    ]
    rows = [header]
    for m in materials[:20]:
        cat = m.get("document_category") or "—"
        rows.append(
            [
                Paragraph(str(m.get("file_name") or "—"), styles["muted"]),
                Paragraph(str(cat), styles["muted"]),
                Paragraph(str(m.get("ocr_engine") or "—"), styles["muted"]),
                Paragraph(_layout_summary(m.get("layout_counts") or {}), styles["muted"]),
            ]
        )
    t = Table(rows, colWidths=[5.5 * cm, 3.2 * cm, 3.5 * cm, 3.3 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A2E38")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#12151C")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#2A3344")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#1E293B")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def _finding_card(finding: dict, styles: dict[str, ParagraphStyle]) -> KeepTogether:
    level = finding.get("risk_level") or "中"
    accent = LEVEL_COLORS.get(level, LEVEL_COLORS["中"])
    bg = LEVEL_BG.get(level, LEVEL_BG["中"])
    rule = finding.get("rule_triggered") or ""
    category = finding.get("risk_category") or ""
    problem = finding.get("problem") or ""
    suggestion = finding.get("suggestion") or ""
    evidence = finding.get("evidence_json") or {}
    evidence_lines = []
    if isinstance(evidence, dict):
        for k, v in list(evidence.items())[:4]:
            evidence_lines.append(f"{k}: {v}")
    evidence_text = " · ".join(evidence_lines) if evidence_lines else "—"

    header = Table(
        [
            [
                Paragraph(f'<font color="{accent.hexval()}"><b>[{level}]</b></font> {problem}', styles["card_title"]),
                Paragraph(f"<b>{rule}</b>", styles["muted"]),
            ]
        ],
        colWidths=[11.5 * cm, 3.5 * cm],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("BOX", (0, 0), (-1, -1), 0.5, accent),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )

    body = Table(
        [
            [Paragraph(f"<b>类别</b>：{category}", styles["body"])],
            [Paragraph(f"<b>证据</b>：{evidence_text}", styles["muted"])],
            [Paragraph(f"<b>建议</b>：{suggestion}", styles["body"])],
        ],
        colWidths=[15 * cm],
    )
    body.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0F1218")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#2A3344")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return KeepTogether([header, body, Spacer(1, 6)])


def _category_breakdown(findings: list[dict], styles: dict[str, ParagraphStyle]) -> Table:
    cats: dict[str, int] = {}
    for f in findings:
        c = f.get("risk_category") or "其他"
        cats[c] = cats.get(c, 0) + 1
    rows = [[Paragraph("<b>类别</b>", styles["body"]), Paragraph("<b>数量</b>", styles["body"])]]
    for cat, n in sorted(cats.items(), key=lambda x: -x[1]):
        bar_w = min(n * 12, 120)
        bar = Table([[""]], colWidths=[bar_w * mm], rowHeights=[4 * mm])
        bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#5EB8D4"))]))
        rows.append([Paragraph(cat, styles["body"]), Table([[bar, Paragraph(str(n), styles["body"])]], colWidths=[bar_w * mm, 1.5 * cm])])
    t = Table(rows, colWidths=[5 * cm, 10 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#2A3344")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#1E293B")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def _on_page(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#0A0C10"))
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    canvas.setStrokeColor(colors.HexColor("#2A3344"))
    canvas.setLineWidth(0.5)
    canvas.line(2 * cm, 1.2 * cm, PAGE_W - 2 * cm, 1.2 * cm)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.setFont(FONT, 7)
    canvas.drawString(2 * cm, 0.7 * cm, "AuditAgent · 会议合规远程观察 · 综合汇报")
    canvas.drawRightString(PAGE_W - 2 * cm, 0.7 * cm, f"第 {canvas.getPageNumber()} 页")
    canvas.restoreState()


def generate_compliance_pdf_report(
    project_name: str,
    findings: list[dict],
    missing: list[dict],
    output: Path,
    *,
    meeting_case: dict | None = None,
    runtime: dict | None = None,
    parsed_materials: list[dict] | None = None,
) -> None:
    """生成会议合规远程观察综合 PDF（可视化图表 + Finding 卡片，非简单表格清单）。"""
    styles = _styles()
    meeting_case = meeting_case or {}
    runtime = runtime or {}
    parsed_materials = parsed_materials or []
    critic = runtime.get("critic") or {}
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.6 * cm,
    )
    story: list = []

    cover = Table(
        [
            [Paragraph("会议合规远程观察", styles["cover_title"])],
            [Paragraph("Remote Observation · Comprehensive Report", styles["cover_sub"])],
            [Spacer(1, 8)],
            [Paragraph(f"<b>{project_name}</b>", styles["h2"])],
            [
                Paragraph(
                    f"会议编码 {meeting_case.get('meeting_code') or '—'} · "
                    f"{meeting_case.get('observation_type') or '远程观察'} · 生成 {now}",
                    styles["muted"],
                )
            ],
        ],
        colWidths=[15 * cm],
    )
    cover.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#12151C")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#5EB8D4")),
                ("TOPPADDING", (0, 0), (-1, -1), 16),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ]
        )
    )
    story.append(cover)
    story.append(Spacer(1, 14))
    story.append(_metric_row(findings, styles))
    story.append(Spacer(1, 12))

    story.append(Paragraph("一、执行管线", styles["h1"]))
    story.append(_pipeline_drawing())
    story.append(Paragraph("资料入库 → GLM-OCR 视觉解析 → 主 Agent 拆解 → 结构化读档 → 子 Agent 规则/比对 → Finding → Critic → 交付", styles["muted"]))
    story.append(Spacer(1, 10))

    info = _meeting_info_table(meeting_case, styles)
    section_no = 2
    if info:
        story.append(Paragraph(f"{_section_num(section_no)}、会议与观察概况", styles["h1"]))
        story.append(info)
        story.append(Spacer(1, 10))
        section_no += 1

    mat_tbl = _material_vision_table(parsed_materials, styles)
    if mat_tbl:
        story.append(Paragraph(f"{_section_num(section_no)}、资料视觉解析（GLM-OCR）", styles["h1"]))
        story.append(
            Paragraph(
                f"共解析 <b>{len(parsed_materials)}</b> 份资料；Markdown 与版面 JSON 见交付包「06_资料解析」。",
                styles["body"],
            )
        )
        story.append(Spacer(1, 6))
        story.append(mat_tbl)
        story.append(Spacer(1, 10))
        section_no += 1

    story.append(Paragraph(f"{_section_num(section_no)}、Finding 分布", styles["h1"]))
    story.append(_level_bar_chart(findings))
    story.append(Paragraph("图例：High=高 · Mid=中 · Low=低", styles["muted"]))
    story.append(Spacer(1, 8))
    story.append(_category_breakdown(findings, styles))
    story.append(Spacer(1, 10))

    if critic:
        section_no += 1
        story.append(Paragraph(f"{_section_num(section_no)}、审核校验 Agent", styles["h1"]))
        critic_tbl = Table(
            [
                [
                    Paragraph(
                        f"已校验 <b>{critic.get('validated', 0)}</b> 条 · "
                        f"疑点 <b>{critic.get('flagged', 0)}</b> 条 · "
                        f"自动重研判 <b>{critic.get('readjudicate_rounds', 0)}</b> 轮",
                        styles["body"],
                    )
                ]
            ],
            colWidths=[15 * cm],
        )
        critic_tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1A2E38")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#5EB8D4")),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        story.append(critic_tbl)
        story.append(Spacer(1, 10))

    story.append(PageBreak())
    section_no += 1
    story.append(Paragraph(f"{_section_num(section_no)}、Finding 明细", styles["h1"]))
    if not findings:
        story.append(Paragraph("本次观察未命中合规 Finding。", styles["body"]))
    else:
        for f in findings[:30]:
            story.append(_finding_card(f, styles))

    if missing:
        story.append(Spacer(1, 8))
        section_no += 1
        story.append(Paragraph(f"{_section_num(section_no)}、资料缺件", styles["h1"]))
        for m in missing[:15]:
            imp = m.get("importance") or "中"
            story.append(
                Paragraph(
                    f"• [{imp}] {m.get('document_type', '')} — {m.get('reason', '')}",
                    styles["body"],
                )
            )

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
