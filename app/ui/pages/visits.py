"""Раздел «Приёмы»: проведённые приёмы, оплата, печатные формы «Назначение лечения» и «Счёт»."""
from __future__ import annotations
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

from app.reports import export
from app.repositories import visits as visits_repo
from app.ui.dialogs.simple import PaymentDialog
from app.ui.models.table_model import Col
from app.ui.pages.base import Page
from app.ui.printing import open_file, temp_pdf_path
from app.ui.widgets.common import GREEN, RED, TableWithEmpty, col_date, col_money, page_header


class VisitsPage(Page):
    title = "Приёмы"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Животное или владелец")
        self.only_debt = QCheckBox("только с долгом")
        self.table = TableWithEmpty([
            col_date("Дата", lambda v: v.appt_date), Col("Животное", lambda v: v.animal_name),
            Col("Владелец", lambda v: v.owner_name), Col("Врач", lambda v: v.vet_name),
            Col("Услуга", lambda v: v.service_name), Col("Диагноз", lambda v: v.diagnosis),
            col_money("Сумма", lambda v: v.price_kopecks), col_money("Оплачено", lambda v: v.paid_kopecks),
            col_money("Долг", lambda v: v.debt_kopecks)],
            row_color=lambda v: RED if v.debt_kopecks > 0 else None, hint="Проведённых приёмов нет.")
        b_pay, b_rx, b_inv = QPushButton("Принять оплату"), QPushButton("Назначение (PDF)"), QPushButton("Счёт (PDF)")
        b_pay.setObjectName("primary")
        self.search.setClearButtonEnabled(True)
        b_pay.clicked.connect(self.pay)
        b_rx.clicked.connect(self.print_prescription)
        b_inv.clicked.connect(self.print_invoice)
        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.only_debt)
        for b in (b_pay, b_rx, b_inv):
            top.addWidget(b)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(page_header("Приёмы", "Проведённые приёмы: долги, оплата, печать назначения и счёта."))
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        self.search.textChanged.connect(lambda *_: self.refresh())
        self.only_debt.toggled.connect(lambda *_: self.refresh())

    def focus_search(self) -> None:
        self.search.setFocus()

    def refresh(self) -> None:
        super().refresh()
        s, d = self.search.text(), self.only_debt.isChecked()
        self.load(lambda c: visits_repo.list_visits(c, s, d), self.table.set_rows)

    def _selected(self):
        v = self.table.selected()
        if v is None:
            QMessageBox.information(self, "Приёмы", "Выберите приём в списке.")
        return v

    def pay(self) -> None:
        v = self._selected()
        if v is None:
            return
        if v.debt_kopecks <= 0:
            QMessageBox.information(self, "Оплата", "По этому приёму долга нет.")
            return
        if PaymentDialog(self.ctx, v.appointment_id, v.debt_kopecks, self).exec():
            self.ctx.data_changed.emit()

    def print_prescription(self) -> None:
        self.print_current()

    def print_current(self) -> None:
        v = self._selected()
        if v is None:
            return
        data = self.ctx.query(lambda c: visits_repo.prescription_print_data(c, v.visit_id), self)
        if data:
            path = temp_pdf_path("naznachenie_")
            export.export_prescription_pdf(path, *data)
            open_file(path)

    def print_invoice(self) -> None:
        v = self._selected()
        if v is None:
            return
        info = self.ctx.query(lambda c: visits_repo.invoice_print_data(c, v.appointment_id), self)
        if info:
            path = temp_pdf_path("schet_")
            export.export_invoice_pdf(path, info)
            open_file(path)
