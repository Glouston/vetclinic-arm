"""Небольшие диалоги: владелец, животное, вакцинация, приход/списание, оплата, новая цена, препарат."""
from __future__ import annotations
import re

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox, QHBoxLayout, QLineEdit, QPushButton,
                               QSpinBox, QWidget)

from app.errors import UserError
from app.repositories import catalog, clients
from app.services import payments, stock_ops
from app.ui.dialogs.base import BaseDialog
from app.util import CURRENCY, fmt_money, is_valid_phone, parse_money, today_iso


def qdate_to_iso(d: QDate) -> str:
    return d.toString("yyyy-MM-dd")


def iso_to_qdate(iso: str) -> QDate:
    return QDate.fromString(iso[:10], "yyyy-MM-dd")


def app_today() -> QDate:
    """Рабочая дата приложения (учитывает VETCLINIC_TODAY), а не системные часы."""
    return iso_to_qdate(today_iso())


def new_date_edit(value: str | None = None) -> QDateEdit:
    e = QDateEdit(iso_to_qdate(value) if value else app_today())
    e.setCalendarPopup(True)
    e.setDisplayFormat("dd.MM.yyyy")
    return e


# ------------------------------------------------------------------ владелец
class OwnerDialog(BaseDialog):
    def __init__(self, ctx, owner=None, phone: str = "", parent=None):
        super().__init__(ctx, "Владелец" if owner else "Новый владелец", parent)
        self.owner, self.created_id = owner, None
        self.name = QLineEdit(owner.full_name if owner else "")
        self.phone = QLineEdit(owner.phone if owner else phone)
        self.phone.setPlaceholderText("+375 29 123-45-67")
        self.address = QLineEdit(owner.address or "" if owner else "")
        self.email = QLineEdit(owner.email or "" if owner else "")
        for label, w in [("ФИО *", self.name), ("Телефон *", self.phone), ("Адрес", self.address), ("Email", self.email)]:
            self.form.addRow(label, w)
            if isinstance(w, QLineEdit):
                w.textChanged.connect(self.validate)
        self.validate()

    def validate(self) -> None:
        ok_name = bool(self.name.text().strip())
        ok_phone = is_valid_phone(self.phone.text())
        email = self.email.text().strip()
        ok_email = not email or bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))
        self.mark(self.name, ok_name)
        self.mark(self.phone, ok_phone)
        self.mark(self.email, ok_email)
        self.set_valid(ok_name and ok_phone and ok_email,
                       "Заполните ФИО, белорусский телефон (+375 XX XXX-XX-XX) и корректный email." if not (ok_name and ok_phone and ok_email) else "")

    def on_accept(self) -> None:
        args = (self.name.text(), self.phone.text(), self.address.text(), self.email.text())
        if self.owner:
            ok, _ = self.ctx.execute(lambda c: clients.update_owner(c, self.owner.id, *args), self)
        else:
            ok, self.created_id = self.ctx.execute(lambda c: clients.create_owner(c, *args), self)
        if ok:
            self.accept()


# ----------------------------------------------------------------- животное
class AnimalDialog(BaseDialog):
    def __init__(self, ctx, animal=None, owner_id: int | None = None, parent=None):
        super().__init__(ctx, "Животное" if animal else "Новое животное", parent)
        self.animal, self.created_id = animal, None
        self.owner = QComboBox()
        self._load_owners(animal.owner_id if animal else owner_id)
        self.new_owner = QPushButton("＋ Новый владелец")
        self.new_owner.clicked.connect(self.on_new_owner)
        owner_row = QHBoxLayout()
        owner_row.setContentsMargins(0, 0, 0, 0)
        owner_row.addWidget(self.owner, 1)
        owner_row.addWidget(self.new_owner)
        owner_wrap = QWidget()
        owner_wrap.setLayout(owner_row)
        self.name = QLineEdit(animal.name if animal else "")
        self.species = QComboBox()
        self.species.setEditable(True)
        self.species.addItems(ctx.query(clients.list_species, self) or [])
        self.species.setCurrentText(animal.species if animal else "")
        self.breed = QLineEdit(animal.breed or "" if animal else "")
        self.has_birth = QCheckBox("указана")
        self.birth = new_date_edit(animal.birth_date if animal and animal.birth_date else None)
        self.has_birth.setChecked(bool(animal and animal.birth_date))
        self.birth.setEnabled(self.has_birth.isChecked())
        self.has_birth.toggled.connect(self.birth.setEnabled)
        self.birth.setMaximumDate(app_today())
        birth_row = QHBoxLayout()
        birth_row.addWidget(self.birth)
        birth_row.addWidget(self.has_birth)
        wrap = QWidget()
        wrap.setLayout(birth_row)
        self.sex = QComboBox()
        self.sex.addItem("не указан", None)
        self.sex.addItem("самец", "M")
        self.sex.addItem("самка", "F")
        if animal and animal.sex:
            self.sex.setCurrentIndex(self.sex.findData(animal.sex))
        for label, w in [("Владелец *", owner_wrap), ("Кличка *", self.name), ("Вид *", self.species),
                         ("Порода", self.breed), ("Дата рождения", wrap), ("Пол", self.sex)]:
            self.form.addRow(label, w)
        self.name.textChanged.connect(self.validate)
        self.species.editTextChanged.connect(self.validate)
        self.validate()

    def _load_owners(self, select_id: int | None = None) -> None:
        self.owner.clear()
        for o in self.ctx.query(lambda c: clients.list_owners(c), self) or []:
            self.owner.addItem(f"{o.full_name} ({o.phone})", o.id)
        if select_id is not None:
            self.owner.setCurrentIndex(max(0, self.owner.findData(select_id)))

    def on_new_owner(self) -> None:
        d = OwnerDialog(self.ctx, parent=self)
        if d.exec():
            self._load_owners(d.created_id)
            self.validate()

    def validate(self) -> None:
        ok_name, ok_sp = bool(self.name.text().strip()), bool(self.species.currentText().strip())
        ok_owner = self.owner.count() > 0
        self.mark(self.name, ok_name)
        self.mark(self.species, ok_sp)
        self.set_valid(ok_name and ok_sp and ok_owner,
                       "Укажите владельца, кличку и вид животного." if ok_owner
                       else "Нет владельцев — нажмите «＋ Новый владелец».")

    def on_accept(self) -> None:
        birth = qdate_to_iso(self.birth.date()) if self.has_birth.isChecked() else None
        owner_id = self.owner.currentData()
        if self.animal:
            ok, _ = self.ctx.execute(lambda c: clients.update_animal(
                c, self.animal.id, owner_id, self.name.text(), self.species.currentText(),
                self.breed.text(), birth, self.sex.currentData()), self)
        else:
            ok, self.created_id = self.ctx.execute(lambda c: clients.create_animal(
                c, owner_id, self.name.text(), self.species.currentText(), self.breed.text(), birth,
                self.sex.currentData()), self)
        if ok:
            self.accept()


# --------------------------------------------------------------- вакцинация
class VaccinationDialog(BaseDialog):
    def __init__(self, ctx, animal_id: int, parent=None):
        super().__init__(ctx, "Добавить вакцинацию", parent)
        self.animal_id = animal_id
        self.med = QComboBox()
        for m in ctx.query(catalog.list_medications, self) or []:
            self.med.addItem(m.name, m.id)
        self.date = new_date_edit()
        self.date.setMaximumDate(app_today())
        self.has_next = QCheckBox("ревакцинация")
        self.has_next.setChecked(True)
        self.next = new_date_edit(qdate_to_iso(app_today().addYears(1)))  # addYears корректен и для 29 февраля
        self.has_next.toggled.connect(self.next.setEnabled)
        row = QHBoxLayout()
        row.addWidget(self.next)
        row.addWidget(self.has_next)
        wrap = QWidget()
        wrap.setLayout(row)
        self.form.addRow("Вакцина", self.med)
        self.form.addRow("Дата вакцинации", self.date)
        self.form.addRow("Следующая", wrap)

        self.date.dateChanged.connect(self.validate)
        self.next.dateChanged.connect(self.validate)
        self.has_next.toggled.connect(self.validate)
        self.validate()

    def validate(self) -> None:
        ok_med = self.med.count() > 0
        ok_next = not self.has_next.isChecked() or self.next.date() > self.date.date()
        self.mark(self.next, ok_next)
        self.set_valid(ok_med and ok_next, "Нет препаратов в справочнике — добавьте препарат через «Приход»."
                       if not ok_med else "Дата ревакцинации должна быть позже даты вакцинации.")

    def on_accept(self) -> None:
        nxt = qdate_to_iso(self.next.date()) if self.has_next.isChecked() else None
        ok, _ = self.ctx.execute(lambda c: clients.add_vaccination(
            c, self.animal_id, self.med.currentData(), qdate_to_iso(self.date.date()), nxt), self)
        if ok:
            self.accept()


# ------------------------------------------------------------------- склад
class ReceiptDialog(BaseDialog):
    """Приход: препарат, серия, количество, срок годности."""

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, "Приход на склад", parent)
        self.med = QComboBox()
        self.reload_meds()
        new_med = QPushButton("Новый препарат…")
        new_med.clicked.connect(self.add_medication)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.med, 1)
        row.addWidget(new_med)
        wrap = QWidget()
        wrap.setLayout(row)
        self.batch = QLineEdit()
        self.qty = QSpinBox()
        self.qty.setRange(0, 100000)
        self.expiry = new_date_edit(qdate_to_iso(app_today().addYears(1)))
        self.expiry.setMinimumDate(app_today())
        for label, w in [("Препарат *", wrap), ("Серия *", self.batch), ("Количество *", self.qty),
                         ("Годен до *", self.expiry)]:
            self.form.addRow(label, w)
        self.batch.textChanged.connect(self.validate)
        self.qty.valueChanged.connect(self.validate)
        self.validate()

    def reload_meds(self) -> None:
        self.med.clear()
        for m in self.ctx.query(catalog.list_medications, self) or []:
            self.med.addItem(f"{m.name}, {m.unit}", m.id)

    def add_medication(self) -> None:
        d = MedicationDialog(self.ctx, self)
        if d.exec():
            self.reload_meds()
            self.med.setCurrentIndex(self.med.findData(d.created_id))

    def validate(self) -> None:
        ok = bool(self.batch.text().strip()) and self.qty.value() > 0 and self.med.count() > 0
        self.mark(self.batch, bool(self.batch.text().strip()))
        self.set_valid(ok, "Укажите серию и количество больше нуля.")

    def on_accept(self) -> None:
        ok, _ = self.ctx.execute(lambda c: stock_ops.receive(
            c, self.med.currentData(), self.batch.text(), self.qty.value(), qdate_to_iso(self.expiry.date()),
            today=self.ctx.today()), self)
        if ok:
            self.accept()


class MedicationDialog(BaseDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(ctx, "Новый препарат", parent)
        self.created_id = None
        self.name, self.unit = QLineEdit(), QLineEdit("мл")
        self.form.addRow("Название *", self.name)
        self.form.addRow("Единица *", self.unit)
        self.name.textChanged.connect(self.validate)
        self.validate()

    def validate(self) -> None:
        self.set_valid(bool(self.name.text().strip() and self.unit.text().strip()), "Заполните название и единицу.")

    def on_accept(self) -> None:
        ok, self.created_id = self.ctx.execute(lambda c: catalog.create_medication(c, self.name.text(), self.unit.text()), self)
        if ok:
            self.accept()


class WriteOffDialog(BaseDialog):
    def __init__(self, ctx, batch, parent=None):
        super().__init__(ctx, "Списание", parent, ok_text="Списать")
        self.batch = batch
        self.qty = QSpinBox()
        self.qty.setRange(0, 1000000)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Брак, истёк срок, утеря…")
        self.form.addRow("Партия", QLineEdit(f"{batch.medication_name}, серия {batch.batch_no} (остаток {batch.qty})"))
        self.form.itemAt(0, self.form.ItemRole.FieldRole).widget().setReadOnly(True)
        self.form.addRow("Количество *", self.qty)
        self.form.addRow("Причина *", self.reason)
        self.qty.valueChanged.connect(self.validate)
        self.reason.textChanged.connect(self.validate)
        self.validate()

    def validate(self) -> None:
        ok = self.qty.value() > 0 and bool(self.reason.text().strip())
        self.mark(self.reason, bool(self.reason.text().strip()))
        self.set_valid(ok, "Укажите количество и причину списания.")

    def on_accept(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        if QMessageBox.question(self, "Подтверждение", f"Списать {self.qty.value()} {self.batch.unit} "
                                f"«{self.batch.medication_name}»?") != QMessageBox.StandardButton.Yes:
            return
        ok, _ = self.ctx.execute(lambda c: stock_ops.write_off(c, self.batch.id, self.qty.value(), self.reason.text()), self)
        if ok:
            self.accept()


# ------------------------------------------------------------------- оплата
class PaymentDialog(BaseDialog):
    """Оплата по записи на приём: заранее (предоплата) или в день приёма; полностью или частично."""

    def __init__(self, ctx, appointment_id: int, debt_kopecks: int, parent=None):
        super().__init__(ctx, "Приём оплаты", parent, ok_text="Принять")
        self.appointment_id, self.debt = appointment_id, debt_kopecks
        self.amount = QLineEdit(f"{debt_kopecks // 100},{debt_kopecks % 100:02d}")
        self.method = QComboBox()
        self.method.addItems(list(payments.METHODS))
        self.form.addRow("К оплате", QLineEdit(fmt_money(debt_kopecks)))
        self.form.itemAt(0, self.form.ItemRole.FieldRole).widget().setReadOnly(True)
        self.form.addRow("Сумма *", self.amount)
        self.form.addRow("Способ", self.method)
        self.amount.textChanged.connect(self.validate)
        self.validate()

    def _amount(self) -> int | None:
        try:
            return parse_money(self.amount.text())
        except UserError:
            return None

    def validate(self) -> None:
        a = self._amount()
        ok = a is not None and 0 < a <= self.debt
        self.mark(self.amount, ok)
        self.set_valid(ok, f"Сумма должна быть больше нуля и не больше долга ({fmt_money(self.debt)}).")

    def on_accept(self) -> None:
        ok, _ = self.ctx.execute(lambda c: payments.accept_payment(
            c, self.appointment_id, self._amount(), self.method.currentText()), self)
        if ok:
            self.accept()


# ------------------------------------------------------------- версия цены
class PriceDialog(BaseDialog):
    def __init__(self, ctx, service_id: int, parent=None):
        super().__init__(ctx, "Новая версия цены", parent)
        self.service_id = service_id
        self.price = QLineEdit()
        self.price.setPlaceholderText("1250,00")
        self.valid_from = new_date_edit()
        self.form.addRow(f"Цена, {CURRENCY} *", self.price)
        self.form.addRow("Действует с *", self.valid_from)
        self.price.textChanged.connect(self.validate)
        self.validate()

    def validate(self) -> None:
        try:
            parse_money(self.price.text())
            ok = bool(self.price.text().strip())
        except UserError:
            ok = False
        self.mark(self.price, ok)
        self.set_valid(ok, "Введите корректную цену.")

    def on_accept(self) -> None:
        ok, _ = self.ctx.execute(lambda c: catalog.add_price_version(
            c, self.service_id, parse_money(self.price.text()), qdate_to_iso(self.valid_from.date())), self)
        if ok:
            self.accept()
