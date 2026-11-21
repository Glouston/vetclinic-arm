"""Раздел «Отчёты»: список отчётов, параметры, таблица результата, XLSX и печать."""
from __future__ import annotations
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox, QStackedLayout, QVBoxLayout, QWidget)

from app.reports import export, queries
from app.repositories import catalog
from app.ui.dialogs.simple import new_date_edit, qdate_to_iso
from app.ui.models.table_model import Col
from app.ui.pages.base import Page
from app.ui.printing import print_html
from app.ui.widgets.common import TableWithEmpty, page_header
from app.util import fmt_date, fmt_money

REPORTS = ["Оперативный: приёмы на дату", "Сводный: выручка по врачам и услугам", "Проблемный: ревакцинация и долги"]
STATUSES = ["запланирован", "подтверждён", "завершён", "отменён"]
REPORT_DESCRIPTIONS = ["Расписание на день и состояние записей", "Выручка за период с итогом",
                       "Кого обзвонить: просрочки и долги"]
NOTES = ["Все записи на выбранную дату; итог — число записей и их сумма.",
         "Выручка = оплаченные платежи (включая предоплату) минус возвраты по дате оплаты; границы периода включены."]


class ReportsPage(Page):
    title = "Отчёты"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.result: queries.ReportResult | None = None
        self.list = QListWidget()
        self.list.setObjectName("reportList")
        for name, desc in zip(REPORTS, REPORT_DESCRIPTIONS):
            item = QListWidgetItem(f"{name}\n{desc}")
            item.setToolTip(desc)
            self.list.addItem(item)
        self.list.setFixedWidth(300)
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.currentRowChanged.connect(self.on_report_changed)

        # параметры (по типу отчёта показываются разные строки)
        self.op_date, self.op_status = new_date_edit(ctx.today()), QComboBox()
        self.op_status.addItem("Все статусы", None)
        for s in STATUSES:
            self.op_status.addItem(s, s)
        year_start = ctx.today()[:4] + "-01-01"
        self.rev_from, self.rev_to, self.rev_cat = new_date_edit(year_start), new_date_edit(), QComboBox()
        self.pr_date, self.pr_days = new_date_edit(), QSpinBox()
        self.pr_days.setRange(0, 3650)
        self.pr_days.setValue(30)
        self.pr_both = QCheckBox("оба условия сразу (И); иначе — любое из двух")
        self.params = [
            [("Дата приёмов", self.op_date), ("Статус", self.op_status)],
            [("Период с", self.rev_from), ("по", self.rev_to), ("Категория услуг", self.rev_cat)],
            [("Контрольная дата", self.pr_date), ("Долг старше, дн.", self.pr_days), ("", self.pr_both)],
        ]
        self.forms = QStackedLayout()
        for rows in self.params:
            w, f = QWidget(), QFormLayout()
            for label, widget in rows:
                f.addRow(label, widget)
            w.setLayout(f)
            self.forms.addWidget(w)
        params_box = QGroupBox("Параметры")
        params_box.setLayout(self.forms)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setObjectName("noteLabel")

        b_run, b_xlsx, b_print = QPushButton("Сформировать"), QPushButton("Excel (XLSX)"), QPushButton("Печать")
        b_xlsx.setToolTip("Выгрузить результат с условиями отбора")
        b_run.setObjectName("primary")
        b_run.clicked.connect(self.run_report)
        b_xlsx.clicked.connect(self.to_xlsx)
        b_print.clicked.connect(self.print_current)
        buttons = QHBoxLayout()
        for b in (b_run, b_xlsx, b_print):
            buttons.addWidget(b)
        buttons.addStretch()

        # без сортировки по клику: порядок задаёт SQL, а строка «ИТОГО» должна оставаться последней
        self.table = TableWithEmpty([], hint="Задайте параметры и нажмите «Сформировать».", sortable=False)
        self.no_data = QLabel("<p style='font-size:16px; color:#6b7280'><b>Данных нет</b></p>"
                              "<p>По заданным условиям ничего не найдено — измените параметры.</p>")
        self.no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_stack = QStackedLayout()
        self.result_stack.addWidget(self.table)
        self.result_stack.addWidget(self.no_data)

        right = QVBoxLayout()
        right.addWidget(params_box)
        right.addWidget(self.note)
        right.addLayout(buttons)
        right.addLayout(self.result_stack, 1)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(page_header("Отчёты", "Выберите отчёт слева, задайте параметры и нажмите «Сформировать»."))
        body = QHBoxLayout()
        body.addWidget(self.list)
        body.addLayout(right, 1)
        lay.addLayout(body, 1)
        self.list.setCurrentRow(0)

    def refresh(self) -> None:
        super().refresh()
        self.ctx.run(catalog.list_categories, self._set_categories, self)

    def _set_categories(self, cats) -> None:
        cur = self.rev_cat.currentData()
        self.rev_cat.clear()
        self.rev_cat.addItem("Все категории", None)
        for c in cats:
            self.rev_cat.addItem(c, c)
        self.rev_cat.setCurrentIndex(max(0, self.rev_cat.findData(cur)))

    def select_report(self, index: int) -> None:
        self.list.setCurrentRow(index)

    def on_report_changed(self, row: int) -> None:
        if row < 0:
            return
        self.forms.setCurrentIndex(row)
        self.note.setText(queries.PROBLEM_NOTE if row == 2 else NOTES[row])
        self.result = None
        self.table.model.columns = []
        self.table.set_rows([])
        self.result_stack.setCurrentWidget(self.table)

    def run_report(self) -> None:
        row = self.list.currentRow()
        if row == 0:
            d, st = qdate_to_iso(self.op_date.date()), self.op_status.currentData()
            fn = lambda c: queries.operational(c, d, st)  # noqa: E731
        elif row == 1:
            f, t, cat = qdate_to_iso(self.rev_from.date()), qdate_to_iso(self.rev_to.date()), self.rev_cat.currentData()
            if f > t:
                QMessageBox.warning(self, "Параметры", "Дата начала периода позже даты окончания.")
                return
            fn = lambda c: queries.revenue(c, f, t, cat)  # noqa: E731
        else:
            d, n, both = qdate_to_iso(self.pr_date.date()), self.pr_days.value(), self.pr_both.isChecked()
            fn = lambda c: queries.problem(c, d, n, both)  # noqa: E731
        self.load(fn, self.show_result)

    def show_result(self, res: queries.ReportResult) -> None:
        self.result = res
        fmts = {"money": fmt_money, "date": fmt_date}
        cols = [Col(title, (lambda r, i=i: r[i]), fmts.get(kind), Qt.AlignmentFlag.AlignRight if kind in ("money", "int")
                    else Qt.AlignmentFlag.AlignLeft) for i, (title, kind) in enumerate(res.columns)]
        self.table.model.beginResetModel()
        self.table.model.columns = cols
        self.table.model.endResetModel()
        rows = res.rows + ([res.total] if res.total else [])
        self.table.set_rows(rows)
        self.result_stack.setCurrentWidget(self.no_data if res.empty else self.table)

    def _require_result(self) -> bool:
        if self.result is None:
            QMessageBox.information(self, "Отчёт", "Сначала сформируйте отчёт.")
            return False
        if self.result.empty:
            QMessageBox.information(self, "Отчёт", "Данных нет — выгружать нечего.")
            return False
        return True

    def to_xlsx(self) -> None:
        if not self._require_result():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить отчёт", f"{self.result.title}.xlsx", "Excel (*.xlsx)")
        if path:
            try:
                export.export_xlsx(self.result, path)  # условия отбора записываются в файл
            except OSError:
                QMessageBox.critical(self, "Выгрузка", "Не удалось сохранить файл. Проверьте путь и права доступа.")
                return
            QMessageBox.information(self, "Выгрузка", f"Отчёт сохранён:\n{path}")

    def print_current(self) -> None:
        if not self._require_result():
            return
        r = self.result
        fmts = {"money": fmt_money, "date": fmt_date}
        head = "".join(f"<th>{t}</th>" for t, _ in r.columns)
        body = "".join("<tr>" + "".join(f"<td>{escape(str(fmts.get(r.columns[i][1], lambda x: x)(v))) if v not in (None, '') else ''}</td>"
                                         for i, v in enumerate(row)) + "</tr>" for row in r.rows + ([r.total] if r.total else []))
        params = "<br>".join(f"<b>{n}:</b> {escape(fmt_date(v) if len(v) == 10 and v[4:5] == '-' else v)}"
                             for n, v in r.params)
        print_html(self, f"<h2>{r.title}</h2><p>{params}</p><table border='1' cellspacing='0' cellpadding='4'>"
                         f"<tr>{head}</tr>{body}</table>")
