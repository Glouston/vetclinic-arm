"""Диалог «Новая запись»: поиск владельца по телефону, фильтр врачей по услуге, свободные слоты."""
from __future__ import annotations
from PySide6.QtCore import QDate, QTime, Qt
from PySide6.QtGui import QBrush, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QWidget)

from app.repositories import appointments as appt_repo
from app.repositories import catalog, clients
from app.services import booking
from app.ui.dialogs.base import BaseDialog
from app.ui.dialogs.simple import AnimalDialog, OwnerDialog, PaymentDialog, app_today, new_date_edit, qdate_to_iso
from PySide6.QtGui import QColor

SLOT_FREE_BG, SLOT_FREE_FG = QColor("#dcfce7"), QColor("#166534")
SLOT_BUSY_BG, SLOT_BUSY_FG = QColor("#f3f4f6"), QColor("#9ca3af")
from app.util import fmt_money, is_valid_phone


class AppointmentDialog(BaseDialog):
    def __init__(self, ctx, animal_id: int | None = None, parent=None):
        super().__init__(ctx, "Новая запись на приём", parent, ok_text="Записать")
        self.created_id = None
        self.owner_id: int | None = None
        self.price: int | None = None

        # --- владелец: телефон с автодополнением --------------------------------
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("Начните вводить телефон или ФИО")
        self.completer = QCompleter()
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.phone.setCompleter(self.completer)
        self.owner_label = QLabel("Владелец не выбран")
        self.create_owner = QPushButton("Создать владельца")
        self.create_owner.setVisible(False)
        self.create_owner.clicked.connect(self.on_create_owner)
        owner_row = QHBoxLayout()
        owner_row.setContentsMargins(0, 0, 0, 0)
        owner_row.addWidget(self.phone, 1)
        owner_row.addWidget(self.create_owner)
        owner_wrap = QWidget()
        owner_wrap.setLayout(owner_row)

        self.animal = QComboBox()
        self.add_animal = QPushButton("＋ Животное")
        self.add_animal.setEnabled(False)
        self.add_animal.clicked.connect(self.on_add_animal)
        animal_row = QHBoxLayout()
        animal_row.setContentsMargins(0, 0, 0, 0)
        animal_row.addWidget(self.animal, 1)
        animal_row.addWidget(self.add_animal)
        animal_wrap = QWidget()
        animal_wrap.setLayout(animal_row)
        self.service = QComboBox()
        self.vet = QComboBox()
        self.date = new_date_edit()
        self.date.setMinimumDate(app_today())
        self.retro = QCheckBox("Ретроспективный ввод (дата в прошлом)")
        self.slots = QListWidget()
        self.slots.setMinimumHeight(118)
        self.slots.setMaximumHeight(160)
        self.slots.setFlow(QListWidget.Flow.LeftToRight)
        self.slots.setWrapping(True)
        self.slots.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.slots.setSpacing(3)
        self.slots.setStyleSheet("QListWidget::item { padding: 5px 9px; border-radius: 6px; }"
                                 "QListWidget::item:selected { background: #0f766e; color: white; }")
        self.slot_legend = QLabel("Зелёные — свободно, серые зачёркнутые — занято. Выберите время.")
        self.slot_legend.setObjectName("legend")
        self.price_label = QLabel("—")
        self.price_label.setObjectName("priceLabel")

        for label, w in [("Телефон владельца *", owner_wrap), ("", self.owner_label), ("Животное *", animal_wrap),
                         ("Услуга *", self.service), ("Врач *", self.vet), ("Дата *", self.date), ("", self.retro),
                         ("Время *", self.slots), ("", self.slot_legend), ("Стоимость", self.price_label)]:
            self.form.addRow(label, w)

        self._load_owner_completer()
        self._load_services()
        self.phone.textChanged.connect(self.on_phone_changed)
        self.completer.activated.connect(self.on_completer_activated)
        self.service.currentIndexChanged.connect(self.on_service_changed)
        self.vet.currentIndexChanged.connect(self.refresh_slots)
        self.date.dateChanged.connect(self.refresh_slots)
        self.retro.toggled.connect(self.on_retro)
        self.slots.currentItemChanged.connect(lambda *_: self.validate())
        if animal_id:
            self._preselect_animal(animal_id)
        self.on_service_changed()
        self.validate()

    # ---- заполнение -------------------------------------------------------
    def _load_owner_completer(self) -> None:
        owners = self.ctx.query(lambda c: clients.list_owners(c), self) or []
        self._owner_by_text = {f"{o.phone} — {o.full_name}": o for o in owners}
        from PySide6.QtCore import QStringListModel
        self.completer.setModel(QStringListModel(list(self._owner_by_text)))

    def _load_services(self) -> None:
        """Услуги сгруппированы по категориям: заголовок категории — недоступный элемент."""
        services = self.ctx.query(lambda c: catalog.list_services(c, self.ctx.today()), self) or []
        model = QStandardItemModel()
        category = object()
        for s in services:
            if s.price_kopecks is None:
                continue
            if s.category != category:
                category = s.category
                head = QStandardItem(f"— {category or 'Прочее'} —")
                head.setFlags(Qt.ItemFlag.NoItemFlags)
                head.setForeground(QBrush(SLOT_BUSY_FG))
                hf = head.font()
                hf.setBold(True)
                head.setFont(hf)
                model.appendRow(head)
            item = QStandardItem(s.name)
            item.setData(s, Qt.ItemDataRole.UserRole)
            model.appendRow(item)
        self.service.setModel(model)
        for i in range(model.rowCount()):  # выбрать первую реальную услугу
            if model.item(i).data(Qt.ItemDataRole.UserRole):
                self.service.setCurrentIndex(i)
                break

    def _preselect_animal(self, animal_id: int) -> None:
        a = self.ctx.query(lambda c: clients.get_animal(c, animal_id, self.ctx.today()), self)
        if a:
            self.phone.setText(a.owner_phone)
            self.animal.setCurrentIndex(max(0, self.animal.findData(animal_id)))

    # ---- владелец ---------------------------------------------------------
    def on_completer_activated(self, text: str) -> None:
        o = self._owner_by_text.get(text)
        if o:
            self.phone.setText(o.phone)

    def on_phone_changed(self) -> None:
        text = self.phone.text().strip()
        owner = self.ctx.query(lambda c: clients.find_owner_by_phone(c, text), self) if text else None
        self.owner_id = owner.id if owner else None
        self.add_animal.setEnabled(owner is not None)
        self._load_animals()
        if owner:
            self.owner_label.setText(f"Владелец: {owner.full_name}")
            self.create_owner.setVisible(False)
        else:
            full = is_valid_phone(text)
            self.owner_label.setText("Владелец с таким телефоном не найден" if full else "Владелец не выбран")
            self.create_owner.setVisible(full)
        self.validate()

    def _load_animals(self, select_id: int | None = None) -> None:
        self.animal.clear()
        if self.owner_id is not None:
            for aid, name, species in self.ctx.query(lambda c: clients.animals_of_owner(c, self.owner_id), self) or []:
                self.animal.addItem(f"{name} ({species})", aid)
        if select_id is not None:
            self.animal.setCurrentIndex(max(0, self.animal.findData(select_id)))

    def on_create_owner(self) -> None:
        d = OwnerDialog(self.ctx, phone=self.phone.text().strip(), parent=self)
        if d.exec():
            self._load_owner_completer()
            self.on_phone_changed()
            if self.owner_id is not None and self.animal.count() == 0:
                self.on_add_animal()  # у нового владельца ещё нет животных — сразу предлагаем добавить

    def on_add_animal(self) -> None:
        d = AnimalDialog(self.ctx, owner_id=self.owner_id, parent=self)
        if d.exec():
            self._load_animals(d.created_id)
            self.validate()

    # ---- услуга / врач / слоты -----------------------------------------------
    def _service(self):
        return self.service.currentData(Qt.ItemDataRole.UserRole)

    def on_service_changed(self) -> None:
        s = self._service()
        self.vet.blockSignals(True)
        self.vet.clear()
        if s:
            for v in self.ctx.query(lambda c: catalog.vets_for_service(c, s.id), self) or []:
                self.vet.addItem(f"{v.full_name} — {v.specialization}", v.id)
            self.price = s.price_kopecks
            self.price_label.setText(fmt_money(s.price_kopecks))
        else:
            self.price = None
            self.price_label.setText("—")
        self.vet.blockSignals(False)
        self.refresh_slots()

    def on_retro(self, on: bool) -> None:
        self.date.setMinimumDate(QDate(2000, 1, 1) if on else app_today())
        self.refresh_slots()

    def refresh_slots(self) -> None:
        self.slots.clear()
        vet_id = self.vet.currentData()
        if vet_id is None:
            self.validate()
            return
        day = qdate_to_iso(self.date.date())
        busy = self.ctx.query(lambda c: appt_repo.busy_times(c, vet_id, day), self) or set()
        # сегодняшние уже прошедшие слоты недоступны (если рабочая дата приложения — реальная)
        now = QTime.currentTime().toString("HH:mm") if day == QDate.currentDate().toString("yyyy-MM-dd") \
            and not self.retro.isChecked() else None
        for t in appt_repo.WORK_SLOTS:
            item = QListWidgetItem(t)
            if t in busy or (now and t <= now):  # занятые и прошедшие недоступны (серые, зачёркнутые)
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setBackground(QBrush(SLOT_BUSY_BG))
                item.setForeground(QBrush(SLOT_BUSY_FG))
                f = item.font()
                f.setStrikeOut(True)
                item.setFont(f)
                item.setToolTip("Занято" if t in busy else "Время уже прошло")
            else:
                item.setBackground(QBrush(SLOT_FREE_BG))  # свободные — зелёные
                item.setForeground(QBrush(SLOT_FREE_FG))
                item.setToolTip("Свободно")
            self.slots.addItem(item)
        self.validate()

    # ---- валидация / сохранение ---------------------------------------------
    def validate(self) -> None:
        checks = [(self.owner_id is not None, self.phone, "Выберите владельца по телефону."),
                  (self.animal.currentData() is not None, self.animal, "У владельца нет животных — нажмите «＋ Животное»."),
                  (self._service() is not None, self.service, "Выберите услугу."),
                  (self.vet.currentData() is not None, self.vet, "Нет врача подходящей специализации."),
                  (self.slots.currentItem() is not None, self.slots, "Выберите свободное время.")]
        for ok, widget, _ in checks:
            if widget is not self.slots:
                self.mark(widget, ok)
        first_bad = next((msg for ok, _, msg in checks if not ok), "")
        self.set_valid(not first_bad, first_bad)

    def on_accept(self) -> None:
        day = qdate_to_iso(self.date.date())
        past = self.date.date() < app_today()
        if past and QMessageBox.question(
                self, "Ретроспективный ввод", "Дата записи в прошлом. Всё равно сохранить?") != QMessageBox.StandardButton.Yes:
            return
        ok, self.created_id = self.ctx.execute(lambda c: booking.create_appointment(
            c, self.animal.currentData(), self.vet.currentData(), self._service().id, day,
            self.slots.currentItem().text(), today=self.ctx.today(), allow_past=past), self)
        if ok:
            self.accept()
            price = self.price or 0
            if price > 0 and QMessageBox.question(
                    self.parentWidget() or self, "Оплата",
                    f"Запись создана. Принять оплату сейчас (предоплата {fmt_money(price)})?\n"
                    "Оплатить можно и позже — в день приёма.") == QMessageBox.StandardButton.Yes:
                PaymentDialog(self.ctx, self.created_id, price, self.parentWidget()).exec()
