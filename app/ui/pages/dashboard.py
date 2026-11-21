"""Главная: плитки-счётчики, ближайшие приёмы, быстрые действия."""
from __future__ import annotations
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.repositories import appointments as appt_repo
from app.ui.models.table_model import Col
from app.ui.pages.base import Page
from app.ui.widgets.common import APPT_STATUS_COLOR, StatTile, TableWithEmpty, col_date, col_money, col_status, page_header


class DashboardPage(Page):
    title = "Главная"
    new_appointment = Signal()
    close_visit = Signal()
    open_reports = Signal()
    open_section = Signal(str)   # клик по плитке: today | unpaid | overdue | expiring

    def __init__(self, ctx):
        super().__init__(ctx)
        self.tiles = {
            "today": StatTile("Приёмов на сегодня", "#0f766e", "Расписание на сегодня →"),
            "unpaid": StatTile("Приёмов ожидают оплаты", "#d97706", "Список долгов →"),
            "overdue": StatTile("Просроченных ревакцинаций", "#dc2626", "Животные с просрочкой →"),
            "expiring": StatTile("Партий препаратов истекает (≤ 30 дн.)", "#ea580c", "Открыть склад →"),
        }
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        for i, (key, t) in enumerate(self.tiles.items()):
            t.setMinimumHeight(130)
            t.clicked.connect(lambda k=key: self.open_section.emit(k))
            grid.addWidget(t, 0, i)
        self.table = TableWithEmpty([
            col_date("Дата", lambda a: a.appt_date), Col("Время", lambda a: a.appt_time),
            Col("Животное", lambda a: a.animal_name), Col("Владелец", lambda a: a.owner_name),
            Col("Врач", lambda a: a.vet_name), Col("Услуга", lambda a: a.service_name),
            col_status("Статус", lambda a: a.status), col_money("Сумма", lambda a: a.price_kopecks)],
            row_color=lambda a: APPT_STATUS_COLOR.get(a.status), hint="Ближайших приёмов нет. Создайте запись (Ctrl+N).")
        b_new, b_close, b_rep = QPushButton("＋  Новая запись"), QPushButton("Закрыть приём"), QPushButton("Сформировать отчёт")
        b_new.setObjectName("primary")
        b_new.setToolTip("Ctrl+N")
        b_close.setToolTip("Откроется список записей: выберите запись и нажмите «Закрыть приём»")
        b_new.clicked.connect(self.new_appointment)
        b_close.clicked.connect(self.close_visit)
        b_rep.clicked.connect(self.open_reports)
        actions = QHBoxLayout()
        for b in (b_new, b_close, b_rep):
            actions.addWidget(b)
        actions.addStretch()
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(page_header("Главная", "Сводка на рабочую дату. Нажмите на плитку, чтобы открыть нужный список."))
        lay.addLayout(grid)
        lay.addLayout(actions)
        sec = QLabel("Ближайшие приёмы")
        sec.setObjectName("sectionTitle")
        lay.addWidget(sec)
        lay.addWidget(self.table, 1)

    def refresh(self) -> None:
        super().refresh()
        today = self.ctx.today()
        self.load(lambda c: (appt_repo.dashboard_stats(c, today), appt_repo.upcoming(c, today, 10)), self._fill)

    def _fill(self, data) -> None:
        stats, rows = data
        self.tiles["today"].set_value(stats.today_appointments)
        self.tiles["unpaid"].set_value(stats.unpaid_visits)
        self.tiles["overdue"].set_value(stats.overdue_vaccinations)
        self.tiles["expiring"].set_value(stats.expiring_batches)
        self.table.set_rows(rows)
