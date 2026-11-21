"""Раздел «Напоминания»: оперативный список, отметка выполнения, генерация."""
from __future__ import annotations
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from app.services import reminders
from app.ui.models.table_model import Col
from app.ui.pages.base import Page
from app.ui.widgets.common import GREEN, RED, YELLOW, TableWithEmpty, col_date, col_status, page_header


def _color(r):
    return {"просрочено": RED}.get(r.status)


class RemindersPage(Page):
    title = "Напоминания"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.status = QComboBox()
        self.status.addItem("Все статусы", None)
        for s in ("запланировано", "просрочено", "выполнено"):
            self.status.addItem(s, s)
        self.table = TableWithEmpty([
            Col("Животное", lambda r: r.animal_name), Col("Владелец", lambda r: r.owner_name),
            Col("Тип", lambda r: r.kind), col_date("Срок", lambda r: r.due_date), col_status("Статус", lambda r: r.status)],
            row_color=_color, hint="Напоминаний нет. Нажмите «Сгенерировать напоминания».")
        b_done, b_gen = QPushButton("Отметить выполненным"), QPushButton("Сгенерировать напоминания")
        b_gen.setObjectName("primary")
        b_gen.setText("Сгенерировать")
        b_gen.setToolTip("Создать недостающие напоминания по ревакцинациям и долгам")
        b_done.clicked.connect(self.mark_done)
        b_gen.clicked.connect(self.generate)
        top = QHBoxLayout()
        top.addWidget(self.status)
        top.addWidget(b_done)
        top.addWidget(b_gen)
        top.addStretch()
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(page_header("Напоминания", "Ревакцинации и неоплаченные приёмы. Сгенерируйте список и отмечайте выполненное."))
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        self.status.currentIndexChanged.connect(lambda *_: self.refresh())

    def refresh(self) -> None:
        super().refresh()
        st, today = self.status.currentData(), self.ctx.today()
        self.load(lambda c: reminders.list_reminders(c, st, today), self.table.set_rows)

    def mark_done(self) -> None:
        r = self.table.selected()
        if r is None:
            QMessageBox.information(self, "Напоминания", "Выберите напоминание.")
            return
        self.ctx.execute(lambda c: reminders.mark_done(c, r.id), self)

    def generate(self) -> None:
        ok, n = self.ctx.execute(lambda c: reminders.generate(c, self.ctx.today()), self)
        if ok:
            QMessageBox.information(self, "Напоминания", f"Создано новых напоминаний: {n}." if n
                                    else "Новых напоминаний нет: все актуальные уже созданы.")
