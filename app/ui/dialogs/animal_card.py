"""Карточка животного: вкладки Владелец | Приёмы | Вакцинации | Назначения | Оплаты | Заметки | Динамика веса."""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QTabWidget, QVBoxLayout, QWidget)

from app.repositories import appointments as appt_repo
from app.repositories import clients
from app.ui.dialogs.simple import AnimalDialog, OwnerDialog, PaymentDialog, VaccinationDialog
from app.ui.widgets.common import TableWithEmpty, col_date, col_money, col_status
from app.ui.models.table_model import Col
from app.ui.widgets.weight_chart import WeightChart
from html import escape

from app.util import fmt_date, fmt_datetime, fmt_money


class AnimalCard(QDialog):
    def __init__(self, ctx, animal_id: int, parent=None):
        super().__init__(parent)
        self.ctx, self.animal_id = ctx, animal_id
        self.setModal(True)
        self.resize(900, 600)
        self.title = QLabel()
        self.title.setObjectName("cardTitle")
        self.tabs = QTabWidget()

        # Владелец
        self.o_name, self.o_phone, self.o_addr, self.o_email = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        owner_tab, form = QWidget(), QFormLayout()
        for label, w in [("ФИО", self.o_name), ("Телефон", self.o_phone), ("Адрес", self.o_addr), ("Email", self.o_email)]:
            form.addRow(label, w)
        save_owner = QPushButton("Сохранить владельца")
        save_owner.setObjectName("primary")
        save_owner.clicked.connect(self.save_owner)
        v = QVBoxLayout(owner_tab)
        v.addLayout(form)
        srow = QHBoxLayout()
        srow.addStretch()
        srow.addWidget(save_owner)
        v.addLayout(srow)
        v.addStretch()
        self.tabs.addTab(owner_tab, "Владелец")

        # Приёмы
        self.t_appts = TableWithEmpty([
            col_date("Дата", lambda a: a.appt_date), Col("Время", lambda a: a.appt_time),
            Col("Врач", lambda a: a.vet_name), Col("Услуга", lambda a: a.service_name),
            col_status("Статус", lambda a: a.status), col_money("Сумма", lambda a: a.price_kopecks),
            col_money("Оплачено", lambda a: a.paid_kopecks)],
            hint="У животного пока не было записей.")
        pay_appt = QPushButton("Принять оплату по записи")
        pay_appt.clicked.connect(self.accept_payment)
        self.tabs.addTab(self._with_button(self.t_appts, pay_appt), "Приёмы")

        # Вакцинации
        self.t_vacc = TableWithEmpty([Col("Вакцина", lambda x: x.medication_name), col_date("Дата", lambda x: x.vacc_date),
                                      col_date("Ревакцинация до", lambda x: x.next_due_date)],
                                     hint="Вакцинаций нет. Нажмите «Добавить вакцинацию».")
        add_v = QPushButton("Добавить вакцинацию")
        add_v.clicked.connect(self.add_vaccination)
        self.tabs.addTab(self._with_button(self.t_vacc, add_v), "Вакцинации")

        # Назначения
        self.t_rx = TableWithEmpty([col_date("Дата", lambda p: p.appt_date), Col("Препарат", lambda p: p.medication_name),
                                    Col("Дозировка", lambda p: p.dosage), Col("Курс, дн.", lambda p: p.course_days),
                                    Col("Кол-во", lambda p: f"{p.qty} {p.unit}"), Col("Врач", lambda p: p.vet_name)],
                                   hint="Назначений нет.")
        self.tabs.addTab(self.t_rx, "Назначения")

        # Оплаты
        self.t_pay = TableWithEmpty([col_date("Приём", lambda p: p.appt_date), Col("Услуга", lambda p: p.service_name),
                                     col_money("Сумма", lambda p: p.amount_kopecks), Col("Способ", lambda p: p.method),
                                     col_status("Статус", lambda p: p.status), Col("Дата оплаты", lambda p: fmt_datetime(p.paid_at))],
                                    hint="Платежей нет. Оплатить можно заранее — на вкладке «Приёмы».")
        self.debt_label = QLabel()
        self.debt_label.setObjectName("debtLabel")
        pay_btn = QPushButton("Принять оплату")
        pay_btn.clicked.connect(self.accept_payment)
        pay_tab = self._with_button(self.t_pay, pay_btn)
        pay_tab.layout().insertWidget(0, self.debt_label)
        self.tabs.addTab(pay_tab, "Оплаты")

        # Заметки
        self.notes = QPlainTextEdit()
        save_notes = QPushButton("Сохранить заметки")
        save_notes.clicked.connect(self.save_notes)
        notes_tab = QWidget()
        nv = QVBoxLayout(notes_tab)
        nv.addWidget(self.notes)
        nv.addWidget(save_notes)
        self.tabs.addTab(notes_tab, "Заметки")

        # Динамика веса
        self.chart = WeightChart()
        self.tabs.addTab(self.chart, "Динамика веса")

        edit, delete, close = QPushButton("Редактировать"), QPushButton("Удалить"), QPushButton("Закрыть")
        delete.setObjectName("danger")
        close.setObjectName("primary")
        printb = QPushButton("Печать")
        edit.clicked.connect(self.edit_animal)
        delete.clicked.connect(self.delete_animal)
        printb.clicked.connect(self.print_card)
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        for b in (edit, delete, printb):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addWidget(self.title)
        lay.addWidget(self.tabs)
        lay.addLayout(row)
        self.reload()

    @staticmethod
    def _with_button(table: TableWithEmpty, button: QPushButton) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(table)
        lay.addWidget(button)
        return w

    def reload(self) -> None:
        def load(c):
            animal = clients.get_animal(c, self.animal_id, self.ctx.today())
            owner = clients.get_owner(c, animal.owner_id) if animal else None
            return (animal, owner, appt_repo.list_appointments(c, animal_id=self.animal_id, newest_first=True),
                    clients.vaccinations_of(c, self.animal_id), clients.prescriptions_of(c, self.animal_id),
                    clients.payments_of(c, self.animal_id), clients.animal_debt_kopecks(c, self.animal_id),
                    clients.weight_points(c, self.animal_id))
        self.ctx.run(load, self._fill, self)

    def _fill(self, data) -> None:
        self.animal, owner, appts, vacc, rx, pays, debt, weights = data
        if self.animal is None:
            self.reject()
            return
        a = self.animal
        self.setWindowTitle(f"Карточка: {a.name}")
        tone = {"просрочена": "#b91c1c", "скоро": "#b45309", "в норме": "#15803d"}.get(a.vacc_status, "#6b7280")
        self.title.setText(f"<span style='font-size:20px; font-weight:700'>{escape(a.name)}</span><br>"
                           f"<span style='color:#6b7280'>{escape(a.species)}{', ' + escape(a.breed) if a.breed else ''} · "
                           f"{'самец' if a.sex == 'M' else 'самка' if a.sex == 'F' else 'пол не указан'} · "
                           f"р. {fmt_date(a.birth_date) or '—'} · владелец {escape(owner.full_name)} · </span>"
                           f"<span style='color:{tone}; font-weight:600'>ревакцинация: {a.vacc_status}</span>")
        self.owner = owner
        self.o_name.setText(owner.full_name)
        self.o_phone.setText(owner.phone)
        self.o_addr.setText(owner.address or "")
        self.o_email.setText(owner.email or "")
        self.t_appts.set_rows(appts)
        self.t_vacc.set_rows(vacc)
        self.t_rx.set_rows(rx)
        self.t_pay.set_rows(pays)
        self.debt_label.setText(f"<b>Текущий долг: {fmt_money(debt)}</b>")
        self.debt = debt
        self.notes.setPlainText(a.notes or "")
        self.chart.set_points(weights)

    def save_owner(self) -> None:
        ok, _ = self.ctx.execute(lambda c: clients.update_owner(
            c, self.owner.id, self.o_name.text(), self.o_phone.text(), self.o_addr.text(), self.o_email.text()), self)
        if ok:
            QMessageBox.information(self, "Сохранено", "Данные владельца сохранены.")
            self.reload()

    def save_notes(self) -> None:
        ok, _ = self.ctx.execute(lambda c: clients.update_animal_notes(c, self.animal_id, self.notes.toPlainText()), self)
        if ok:
            QMessageBox.information(self, "Сохранено", "Заметки сохранены.")

    def add_vaccination(self) -> None:
        if VaccinationDialog(self.ctx, self.animal_id, self).exec():
            self.reload()

    def accept_payment(self) -> None:
        """Оплата по записи: выбранной на вкладке «Приёмы» или по выбранному платежу «ожидает»."""
        appt = self.t_appts.selected()
        pay = self.t_pay.selected()
        if self.tabs.tabText(self.tabs.currentIndex()) == "Оплаты" and pay is not None:
            appt = next((a for a in self.t_appts.model._rows if a.id == pay.appointment_id), None)
        if appt is None:
            QMessageBox.information(self, "Оплата", "Выберите запись на вкладке «Приёмы» "
                                                    "(или неоплаченный платёж на вкладке «Оплаты»).")
            return
        debt = appt.price_kopecks - appt.paid_kopecks
        if appt.status == "отменён" or debt <= 0:
            QMessageBox.information(self, "Оплата", "По этой записи оплачивать нечего: "
                                    + ("запись отменена." if appt.status == "отменён" else "она уже оплачена."))
            return
        if PaymentDialog(self.ctx, appt.id, debt, self).exec():
            self.reload()

    def edit_animal(self) -> None:
        if AnimalDialog(self.ctx, self.animal, parent=self).exec():
            self.reload()

    def delete_animal(self) -> None:
        if QMessageBox.question(self, "Удаление", f"Удалить животное «{self.animal.name}»?") != QMessageBox.StandardButton.Yes:
            return
        ok, _ = self.ctx.execute(lambda c: clients.delete_animal(c, self.animal_id), self)
        if ok:
            self.accept()

    def print_card(self) -> None:
        from app.ui.printing import print_html
        a = self.animal
        rows = "".join(f"<tr><td>{fmt_date(x.appt_date)}</td><td>{escape(x.service_name)}</td><td>{escape(x.vet_name)}</td>"
                       f"<td>{x.status}</td><td>{fmt_money(x.price_kopecks)}</td></tr>" for x in self.t_appts.model._rows)
        print_html(self, f"<h2>Карточка животного: {escape(a.name)}</h2><p>{escape(a.species)}, владелец: "
                         f"{escape(self.owner.full_name)}, {self.owner.phone}</p><table border='1' cellspacing='0' cellpadding='4'>"
                         f"<tr><th>Дата</th><th>Услуга</th><th>Врач</th><th>Статус</th><th>Сумма</th></tr>{rows}</table>")
