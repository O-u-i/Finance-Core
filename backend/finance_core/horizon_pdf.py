from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs" / "horizon" / "finance-core-v3.0.0-horizon.md"
OUTPUT = ROOT / "docs" / "pdf" / "finance-core-v3.0.0-horizon.pdf"
FONT = "FCHorizon"
FONT_PATH = Path(r"C:\Windows\Fonts\simhei.ttf")


def footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D5E3DC"))
    canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
    canvas.setFont(FONT, 8)
    canvas.setFillColor(colors.HexColor("#557066"))
    canvas.drawString(18 * mm, 9 * mm, "Finance Core 3.0.0 · Project Horizon · Candidate directions are not commitments")
    canvas.drawRightString(192 * mm, 9 * mm, f"{document.page}")
    canvas.restoreState()


def inline_markup(value: str) -> str:
    escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"`([^`]+)`", r'<font name="Courier" color="#176B52">\1</font>', escaped)


def build() -> Path:
    if not FONT_PATH.is_file():
        raise FileNotFoundError(f"Required report font not found: {FONT_PATH}")
    pdfmetrics.registerFont(TTFont(FONT, str(FONT_PATH)))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "TitleCN", parent=styles["Title"], fontName=FONT, fontSize=25, leading=34,
        textColor=colors.HexColor("#0B3328"), alignment=TA_LEFT, spaceAfter=12,
    )
    subtitle = ParagraphStyle(
        "SubtitleCN", fontName=FONT, fontSize=11, leading=18, textColor=colors.HexColor("#557066"),
    )
    h1 = ParagraphStyle(
        "H1CN", fontName=FONT, fontSize=16, leading=23, textColor=colors.HexColor("#0B5D47"),
        spaceBefore=13, spaceAfter=8, keepWithNext=True,
    )
    h2 = ParagraphStyle(
        "H2CN", fontName=FONT, fontSize=12, leading=18, textColor=colors.HexColor("#194F3F"),
        spaceBefore=9, spaceAfter=5, keepWithNext=True,
    )
    body = ParagraphStyle(
        "BodyCN", fontName=FONT, fontSize=9.5, leading=16, textColor=colors.HexColor("#243C34"),
        spaceAfter=6, alignment=TA_LEFT,
    )
    bullet = ParagraphStyle(
        "BulletCN", parent=body, leftIndent=12, firstLineIndent=-8, bulletIndent=2, spaceAfter=4,
    )
    small = ParagraphStyle(
        "SmallCN", fontName=FONT, fontSize=8.5, leading=14, textColor=colors.HexColor("#557066"),
    )
    document = SimpleDocTemplate(
        str(OUTPUT), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=20 * mm,
        title="Finance Core v3.0.0 Project Horizon",
        author="Finance Core",
        subject="Current capabilities, boundaries, and candidate expansion horizons",
    )
    story = [
        Spacer(1, 16 * mm),
        Paragraph("Finance Core", subtitle),
        Paragraph("v3.0.0 Project Horizon", title),
        Paragraph("多数据空间、确定性账本与未来扩展边界", ParagraphStyle("Cover", parent=h1, fontSize=15)),
        Spacer(1, 8 * mm),
        Table(
            [
                ["Service / API", "3.0.0 / 3.0.0"],
                ["Ledger / Registry schema", "2 / 1"],
                ["生成日期", "2026-09-03"],
                ["文档性质", "Horizon - 候选方向，不是交付承诺"],
            ],
            colWidths=[55 * mm, 105 * mm],
            style=TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E7F2ED")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#0B5D47")),
                ("GRID", (0, 0), (-1, -1), .5, colors.HexColor("#B9CEC5")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]),
        ),
        Spacer(1, 10 * mm),
        Paragraph("阅读提示", h2),
        Paragraph("本报告严格区分“当前已实现”与“未来可扩展”。任何 Horizon 条目都不能被当作 capability、发布承诺或自动实施授权。", body),
        PageBreak(),
    ]
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            story.append(Paragraph(inline_markup(" ".join(paragraph)), body))
            paragraph.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if stripped.startswith("# ") or stripped.startswith("生成日期："):
            continue
        if stripped.startswith("## "):
            flush()
            story.append(Paragraph(inline_markup(stripped[3:]), h1))
            continue
        if stripped.startswith("### "):
            flush()
            heading = Paragraph(inline_markup(stripped[4:]), h2)
            story.append(KeepTogether([heading]))
            continue
        if stripped.startswith("- "):
            flush()
            story.append(Paragraph(inline_markup(f"- {stripped[2:]}"), bullet))
            continue
        paragraph.append(stripped)
    flush()
    story.extend([
        Spacer(1, 8 * mm),
        Table(
            [[Paragraph("边界结论", h2)], [Paragraph("FC 的长期价值来自可验证的确定性财务核心。扩展速度不能以牺牲 Vault 隔离、不可变账本、Decimal 合同、人工确认和隐私边界为代价。", body)]],
            colWidths=[160 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDF0E8")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F4F8F6")),
                ("BOX", (0, 0), (-1, -1), .8, colors.HexColor("#7DAE9C")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]),
        )
    ])
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return OUTPUT


if __name__ == "__main__":
    print(build())
