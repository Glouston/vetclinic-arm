"""Раздел «Записи на приём»: список, фильтры, смена статусов, закрытие приёма."""
from __future__ import annotations
from datetime import date, timedelta

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

from app.repositories import appointments as appt_repo
from app.repositories import catalog
from app.repositories import visits as visits_repo
from app.reports import export
from app.ui.printing import open_file, temp_pdf_path
from app.util import fmt_date, fmt_money
from app.services import booking
from app.ui.dialogs.appointment import AppointmentDialog
from app.ui.dialogs.simple import PaymentDialog, iso_to_qdate, new_date_edit, qdate_to_iso
from app.ui.dialogs.visit import CloseVisitDialog
from app.ui.models.table_model import Col
from app.ui.pages.base import Page
from app.ui.widgets.common import TableWithEmpty, col_date, col_money, col_status, page_header

STATUSES = ["запланирован", "подтверждён", "завершён", "отменён"]


class AppointmentsPage(Page):
    title = "Записи на приём"

    def __init__(self, ctx):
        super().__init__(ctx)
        today = date.fromisoformat(ctx.today())
        self.d_from = new_date_edit((today - timedelta(days=30)).isoformat())
        self.d_to = new_date_edit((today + timedelta(days=60)).isoformat())
        self.status = QComboBox()
        self.status.addItem("Все статусы", None)
        for s in STATUSES:
            self.status.addItem(s, s)
        self.vet = QComboBox()
        self.vet.setMinimumWidth(190)
        self.status.setMinimumWidth(140)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск: кличка или владелец   (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        b_reset = QPushButton("Сбросить")
        b_reset.setObjectName("link")
        b_reset.clicked.connect(self.reset_filters)
        self.table = TableWithEmpty([
            col_date("Дата", lambda a: a.appt_date), Col("Время", lambda a: a.appt_time),
            Col("Животное", lambda a: a.animal_name), Col("Владелец", lambda a: a.owner_name),
            Col("Врач", lambda a: a.vet_name), Col("Услуга", lambda a: a.service_name),
            col_status("Статус", lambda a: a.status), col_money("Сумма", lambda a: a.price_kopecks),
            col_money("Оплачено", lambda a: a.paid_kopecks)],
            hint="Нет записей за выбранный период. Измените фильтры или создайте запись (Ctrl+N).")
        self.table.selection_changed.connect(self.update_buttons)
        self.b_new, self.b_confirm = QPushButton("＋  Новая запись"), QPushButton("Подтвердить")
        self.b_cancel, self.b_close = QPushButton("Отменить"), QPushButton("Закрыть приём")
        self.b_pay = QPushButton("Принять оплату")
        self.b_pay.setToolTip("Оплата возможна сразу после записи (предоплата) или в день приёма")
        self.b_invoice = QPushButton("Счёт (PDF)")
        self.b_cancel.setObjectName("danger")
        self.action_hint = QLabel()
        self.action_hint.setObjectName("actionHint")
        self.b_invoice.clicked.connect(self.print_current)
        self.b_new.setObjectName("primary")
        self.b_new.clicked.connect(self.new_appointment)
        self.b_confirm.clicked.connect(lambda: self.set_status("подтверждён"))
        self.b_cancel.clicked.connect(self.cancel)
        self.b_close.clicked.connect(self.close_visit)
        self.b_pay.clicked.connect(self.pay)

        filters = QHBoxLayout()
        filters.addWidget(self.search, 1)
        for label, w in [("Период", self.d_from), ("—", self.d_to), ("", self.status), ("", self.vet)]:
            if label:
                filters.addWidget(QLabel(label))
            filters.addWidget(w)
        filters.addWidget(b_reset)
        # кнопки сгруппированы по смыслу: создать | статус записи | деньги
        buttons = QHBoxLayout()
        buttons.addWidget(self.b_new)
        buttons.addSpacing(16)
        for b in (self.b_confirm, self.b_close, self.b_cancel):
            buttons.addWidget(b)
        buttons.addSpacing(16)
        for b in (self.b_pay, self.b_invoice):
            buttons.addWidget(b)
        buttons.addStretch()
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(page_header("Записи на приём", "Запишите клиента, подтвердите визит, закройте приём и примите "
                                  "оплату — заранее или в день приёма."))
        lay.addLayout(filters)
        lay.addLayout(buttons)
        lay.addWidget(self.action_hint)
        lay.addWidget(self.table, 1)
        self.count = QLabel()
        self.count.setObjectName("countLabel")
        lay.addWidget(self.count)
        self.update_buttons()
        self._vets_loaded = False
        for sig in (self.d_from.dateChanged, self.d_to.dateChanged, self.status.currentIndexChanged,
                    self.vet.currentIndexChanged, self.search.textChanged):
            sig.connect(lambda *_: self.refresh())

    def focus_search(self) -> None:
        self.search.setFocus()

    def reset_filters(self) -> None:
        today = date.fromisoformat(self.ctx.today())
        for w in (self.d_from, self.d_to, self.status, self.vet, self.search):
            w.blockSignals(True)
        self.d_from.setDate(iso_to_qdate((today - timedelta(days=30)).isoformat()))
        self.d_to.setDate(iso_to_qdate((today + timedelta(days=60)).isoformat()))
        self.status.setCurrentIndex(0)
        self.vet.setCurrentIndex(0)
        self.search.clear()
        for w in (self.d_from, self.d_to, self.status, self.vet, self.search):
            w.blockSignals(False)
        self.refresh()

    def show_day(self, day: str) -> None:
        """Показать записи одного дня (переход с плитки «Приёмов на сегодня»)."""
        for w in (self.d_from, self.d_to):
            w.blockSignals(True)
            w.setDate(iso_to_qdate(day))
            w.blockSignals(False)
        self.refresh()

    def refresh(self) -> None:
        super().refresh()
        f, t = qdate_to_iso(self.d_from.date()), qdate_to_iso(self.d_to.date())
        st, vet, s = self.status.currentData(), self.vet.currentData(), self.search.text()
        self.load(lambda c: (appt_repo.list_appointments(c, f, t, st, vet, s), catalog.list_vets(c)), self._fill)

    def _fill(self, data) -> None:
        rows, vets = data
        if self.vet.count() != len(vets) + 1:  # новый/удалённый врач — обновить список фильтра
            self._vets_reload(vets)
        self.table.set_rows(rows)
        self.count.setText(f"Записей: {len(rows)}")
        self.update_buttons()

    def update_buttons(self) -> None:
        """Кнопки активны только при допустимом переходе статуса."""
        a = self.table.selected()
        st = a.status if a else None
        self.b_confirm.setEnabled(bool(st) and booking.can_transition(st, "подтверждён"))
        self.b_cancel.setEnabled(bool(st) and booking.can_transition(st, "отменён"))
        self.b_close.setEnabled(bool(st) and booking.can_transition(st, "завершён"))
        self.b_pay.setEnabled(bool(a) and a.status != "отменён" and a.price_kopecks - a.paid_kopecks > 0)
        self.b_invoice.setEnabled(bool(a) and a.status != "отменён")
        self.action_hint.setText(self._hint(a))

    @staticmethod
    def _hint(a) -> str:
        """Объясняет, что можно сделать с выбранной записью (почему кнопки активны/неактивны)."""
        if a is None:
            return "Выберите запись в таблице — станут доступны действия с ней."
        left = a.price_kopecks - a.paid_kopecks
        pay = f"к оплате {fmt_money(left)}" if left > 0 else "оплачено полностью"
        return {
            "запланирован": f"Запись запланирована: можно подтвердить, закрыть приём, отменить или принять оплату заранее ({pay}).",
            "подтверждён": f"Запись подтверждена: можно закрыть приём или отменить; оплата — заранее или в день приёма ({pay}).",
            "завершён": f"Приём завершён и не может быть изменён; {pay}.",
            "отменён": "Запись отменена — действия недоступны (внесённая оплата возвращена).",
        }.get(a.status, "")

    # ---- действия ------------------------------------------------------------
    def new_appointment(self, animal_id: int | None = None) -> None:
        AppointmentDialog(self.ctx, animal_id if isinstance(animal_id, int) else None, self).exec()

    def _vets_reload(self, vets) -> None:
        cur = self.vet.currentData()
        self.vet.blockSignals(True)
        self.vet.clear()
        self.vet.addItem("Все врачи", None)
        for v in vets:
            self.vet.addItem(v.full_name, v.id)
        self.vet.setCurrentIndex(max(0, self.vet.findData(cur)))
        self.vet.blockSignals(False)

    def set_status(self, status: str) -> None:
        a = self.table.selected()
        if a:
            self.ctx.execute(lambda c: booking.change_status(c, a.id, status), self)

    def cancel(self) -> None:
        a = self.table.selected()
        refund = f"\nВнесённая оплата {fmt_money(a.paid_kopecks)} будет оформлена как возврат." if a and a.paid_kopecks > 0 else ""
        if a and QMessageBox.question(self, "Отмена записи", f"Отменить запись: {a.animal_name}, "
                                      f"{fmt_date(a.appt_date)} {a.appt_time}?{refund}") == QMessageBox.StandardButton.Yes:
            self.set_status("отменён")

    def close_visit(self) -> None:
        a = self.table.selected()
        if a is None:
            QMessageBox.information(self, "Закрыть приём", "Выберите запись в списке.")
            return
        future = a.appt_date > self.ctx.today()
        if future and QMessageBox.question(
                self, "Закрыть приём", f"Приём назначен на {fmt_date(a.appt_date)} — это будущая дата. "
                "Всё равно закрыть его сейчас?") != QMessageBox.StandardButton.Yes:
            return
        if CloseVisitDialog(self.ctx, a, self, allow_future=future).exec():
            self.ctx.data_changed.emit()

    def pay(self) -> None:
        a = self.table.selected()
        if a and PaymentDialog(self.ctx, a.id, a.price_kopecks - a.paid_kopecks, self).exec():
            self.ctx.data_changed.emit()

    def print_current(self) -> None:
        """Счёт по выбранной записи (можно выставить заранее — для предоплаты)."""
        a = self.table.selected()
        if a is None:
            QMessageBox.information(self, "Счёт", "Выберите запись в списке.")
            return
        info = self.ctx.query(lambda c: visits_repo.invoice_print_data(c, a.id), self)
        if info:
            path = temp_pdf_path("schet_")
            export.export_invoice_pdf(path, info)
            open_file(path)
