"""Выгрузка отчёта в XLSX (openpyxl) и печатные формы в PDF (reportlab)."""
from __future__ import annotations
from decimal import Decimal
from html import escape
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.reports.queries import ReportResult
from app.util import fmt_date, fmt_money, now_str

RUB_FORMAT = '#,##0.00" BYN"'
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
_FONT_BOLD_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _cell(kind: str, value):
    if value is None or value == "":
        return None
    if kind == "money":
        return Decimal(int(value)) / 100
    if kind == "date":
        return fmt_date(value)
    return value


def export_xlsx(result: ReportResult, path: str | Path) -> None:
    """Лист с заголовком, условиями отбора, таблицей и итогом; кириллица — в UTF-8 (xlsx)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Отчёт"
    ws.append([result.title])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"Сформирован: {fmt_date(now_str())} {now_str()[11:16]}"])
    for name, value in result.params:
        ws.append([f"{name}:", fmt_date(value) if len(value) == 10 and value[4] == "-" else value])
    ws.append([])
    head_row = ws.max_row + 1
    ws.append([c[0] for c in result.columns])
    thin = Side(style="thin", color="999999")
    for cell in ws[head_row]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2F6F8F")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
    if result.empty:
        ws.append(["Данных нет"])
    for row in result.rows + ([result.total] if result.total else []):
        ws.append([_cell(result.columns[i][1], v) for i, v in enumerate(row)])
        for i, cell in enumerate(ws[ws.max_row]):
            cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
            if result.columns[i][1] == "money":
                cell.number_format = RUB_FORMAT
    if result.total:
        for cell in ws[ws.max_row]:
            cell.font = Font(bold=True)
    for i in range(1, len(result.columns) + 1):
        width = max((len(str(c.value)) for c in ws[get_column_letter(i)] if c.value is not None), default=10)
        ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 12), 45)
    ws.freeze_panes = ws.cell(row=head_row + 1, column=1)
    wb.save(str(path))


def _register_fonts() -> tuple[str, str]:
    for regular, bold in zip(_FONT_CANDIDATES, _FONT_BOLD_CANDIDATES):
        if Path(regular).exists():
            pdfmetrics.registerFont(TTFont("VC", regular))
            pdfmetrics.registerFont(TTFont("VC-Bold", bold if Path(bold).exists() else regular))
            pdfmetrics.registerFontFamily("VC", normal="VC", bold="VC-Bold", italic="VC", boldItalic="VC-Bold")
            return "VC", "VC-Bold"
    for regular in _FONT_CANDIDATES:  # хотя бы любой шрифт с кириллицей
        if Path(regular).exists():
            pdfmetrics.registerFont(TTFont("VC", regular))
            return "VC", "VC"
    raise RuntimeError("Не найден шрифт с поддержкой кириллицы для PDF.")


def _styles():
    regular, bold = _register_fonts()
    ss = getSampleStyleSheet()
    return (ParagraphStyle("t", parent=ss["Title"], fontName=bold, fontSize=16),
            ParagraphStyle("n", parent=ss["Normal"], fontName=regular, fontSize=10, leading=14),
            regular, bold)


def _table(data, col_widths, regular, bold, total_row=False):
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [("FONT", (0, 0), (-1, -1), regular, 9), ("FONT", (0, 0), (-1, 0), bold, 9),
             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F6F8F")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
             ("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    if total_row:
        style.append(("FONT", (0, -1), (-1, -1), bold, 9))
    t.setStyle(TableStyle(style))
    return t


def export_prescription_pdf(path: str | Path, info: dict, items: list[dict]) -> None:
    """Печатная форма «Назначение лечения». info: animal, species, owner, vet, date, diagnosis."""
    title, normal, regular, bold = _styles()
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm)
    story = [Paragraph("Назначение лечения", title), Spacer(1, 6)]
    for label, key in [("Дата приёма", "date"), ("Животное", "animal"), ("Владелец", "owner"),
                       ("Врач", "vet"), ("Диагноз", "diagnosis")]:
        story.append(Paragraph(f"<b>{label}:</b> {escape(str(info.get(key) or '—'))}", normal))
    story.append(Spacer(1, 10))
    data = [["Препарат", "Дозировка", "Курс, дн.", "Кол-во"]] + [
        [i["medication"], i["dosage"], i["course_days"] or "—", f"{i['qty']} {i['unit']}"] for i in items]
    if not items:
        data.append(["Назначений нет", "", "", ""])
    story += [_table(data, [60 * mm, 60 * mm, 25 * mm, 25 * mm], regular, bold), Spacer(1, 24),
              Paragraph("Подпись врача: ____________________", normal)]
    doc.build(story)


def export_invoice_pdf(path: str | Path, info: dict) -> None:
    """Печатная форма «Счёт». info: number, date, animal, owner, service, vet, price, paid (копейки)."""
    title, normal, regular, bold = _styles()
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm)
    story = [Paragraph(f"Счёт № {info['number']} от {fmt_date(info['date'])}", title), Spacer(1, 6)]
    info = {**info, "visit": f"{fmt_date(info['date'])} {info.get('time') or ''}".strip()}
    for label, key in [("Плательщик", "owner"), ("Животное", "animal"), ("Врач", "vet"), ("Приём", "visit")]:
        story.append(Paragraph(f"<b>{label}:</b> {escape(str(info.get(key) or '—'))}", normal))
    story.append(Spacer(1, 10))
    debt = info["price"] - info["paid"]
    data = [["Услуга", "Сумма"], [info["service"], fmt_money(info["price"])],
            ["Оплачено (в т.ч. предоплата)", fmt_money(info["paid"])], ["К оплате", fmt_money(max(debt, 0))]]
    story.append(_table(data, [120 * mm, 50 * mm], regular, bold, total_row=True))
    doc.build(story)


def export_report_pdf(result: ReportResult, path: str | Path) -> None:
    """PDF-версия отчёта (для печати)."""
    title, normal, regular, bold = _styles()
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=15 * mm)
    story = [Paragraph(escape(result.title), title)]
    for name, value in result.params:
        story.append(Paragraph(f"<b>{escape(name)}:</b> {escape(str(value))}", normal))
    story.append(Spacer(1, 8))
    if result.empty:
        story.append(Paragraph("Данных нет", normal))
    else:
        def fmt(kind, v):
            return fmt_money(v) if kind == "money" and v is not None else (fmt_date(v) if kind == "date" else ("" if v is None else str(v)))
        rows = result.rows + ([result.total] if result.total else [])
        data = [[c[0] for c in result.columns]] + [[fmt(result.columns[i][1], v) for i, v in enumerate(r)] for r in rows]
        width = (A4[0] - 24 * mm) / len(result.columns)
        story.append(_table(data, [width] * len(result.columns), regular, bold, total_row=bool(result.total)))
    doc.build(story)
