"""Раздел «Склад»: партии, приход, списание с причиной, фильтр «истекает в течение N дней»."""
from __future__ import annotations
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout)

from app.repositories import stock
from app.ui.dialogs.simple import ReceiptDialog, WriteOffDialog
from app.ui.models.table_model import Col
from app.ui.pages.base import Page
from app.ui.widgets.common import BATCH_COLOR, TableWithEmpty, col_date, col_status, page_header


class StockPage(Page):
    title = "Склад"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Препарат или серия")
        self.expiring = QCheckBox("истекает в течение")
        self.days = QSpinBox()
        self.days.setRange(1, 730)
        self.days.setValue(30)
        self.days.setSuffix(" дн.")
        self.table = TableWithEmpty([
            Col("Препарат", lambda b: b.medication_name), Col("Серия", lambda b: b.batch_no),
            Col("Остаток", lambda b: b.qty, lambda v: str(v)), Col("Ед.", lambda b: b.unit),
            col_date("Годен до", lambda b: b.expiry_date), col_status("Срок", lambda b: b.state)],
            row_color=lambda b: BATCH_COLOR.get(b.state), hint="Партий нет. Нажмите «Приход».")
        b_in, b_out = QPushButton("＋  Приход"), QPushButton("Списание…")
        b_out.setObjectName("danger")
        self.search.setClearButtonEnabled(True)
        b_in.setObjectName("primary")
        b_in.clicked.connect(self.receive)
        b_out.clicked.connect(self.write_off)
        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.expiring)
        top.addWidget(self.days)
        top.addWidget(b_in)
        top.addWidget(b_out)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(page_header("Склад", "Партии препаратов и сроки годности. Приход — новая партия; списание — только с причиной."))
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        legend = QLabel("Зелёный — в норме, жёлтый — истекает (≤ 30 дн.), красный — просрочен "
                        "(просроченные партии не списываются на приёмах).")
        legend.setObjectName("legend")
        lay.addWidget(legend)
        for sig in (self.search.textChanged, self.expiring.toggled, self.days.valueChanged):
            sig.connect(lambda *_: self.refresh())

    def focus_search(self) -> None:
        self.search.setFocus()

    def refresh(self) -> None:
        super().refresh()
        s, days, today = self.search.text(), (self.days.value() if self.expiring.isChecked() else None), self.ctx.today()
        self.load(lambda c: stock.list_batches(c, today, days, s), self.table.set_rows)

    def receive(self) -> None:
        if ReceiptDialog(self.ctx, self).exec():
            self.ctx.data_changed.emit()

    def write_off(self) -> None:
        b = self.table.selected()
        if b is None:
            QMessageBox.information(self, "Списание", "Выберите партию в таблице.")
            return
        if WriteOffDialog(self.ctx, b, self).exec():
            self.ctx.data_changed.emit()
