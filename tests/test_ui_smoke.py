"""Smoke-тесты UI (pytest-qt, offscreen): окно, навигация, диалоги, отмена без сохранения, откат транзакции."""
from __future__ import annotations
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QDate, Qt  # noqa: E402
from PySide6.QtWidgets import QDialog, QMessageBox  # noqa: E402

from app import db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.repositories import appointments as appt_repo  # noqa: E402
from app.repositories import clients  # noqa: E402
from app.ui.dialogs.appointment import AppointmentDialog  # noqa: E402
from app.ui.dialogs.animal_card import AnimalCard  # noqa: E402
from app.ui.dialogs.visit import CloseVisitDialog  # noqa: E402
from tests.conftest import TODAY  # noqa: E402


@pytest.fixture
def window(qtbot, db_path, monkeypatch):
    monkeypatch.setenv("VETCLINIC_TODAY", TODAY)
    shown = []
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, _n=name, **k: shown.append((_n, a[2] if len(a) > 2 else ""))))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    # предложение предоплаты после записи открывает модальный диалог — в тестах только фиксируем вызов
    import app.ui.dialogs.appointment as appt_dialog_mod
    offers = []
    monkeypatch.setattr(appt_dialog_mod, "PaymentDialog",
                        lambda ctx, appt_id, amount, parent=None: type("D", (), {"exec": lambda self: offers.append((appt_id, amount)) or 0})())
    _, w = create_app(db_path)
    qtbot.addWidget(w)
    w.show()
    w.messages = shown
    w.prepay_offers = offers
    return w


def test_t29_ui_main_window_and_navigation(qtbot, window):
    """T-29 | UI: главное окно открывается, навигация по всем разделам | перебрать пункты списка | страница меняется, дашборд заполнен."""
    assert window.nav.count() == 10
    qtbot.waitUntil(lambda: window.dashboard.tiles["today"].value.text() != "—", timeout=5000)
    assert int(window.dashboard.tiles["today"].value.text()) > 0
    for i in range(window.nav.count()):
        window.nav.setCurrentRow(i)
        assert window.stack.currentIndex() == i
    window.nav.setCurrentRow(1)
    qtbot.waitUntil(lambda: window.pages["Животные"].table.row_count() == 30, timeout=5000)


def test_t30_ui_animals_filters_and_empty_state(qtbot, window):
    """T-30 | UI: поиск + фильтры вместе, пустое состояние | ввести несуществующий поиск | таблица скрыта, показана заглушка «Нет данных»."""
    page = window.pages["Животные"]
    window.nav.setCurrentRow(1)
    qtbot.waitUntil(lambda: page.table.row_count() > 0, timeout=5000)
    page.overdue.setChecked(True)
    qtbot.waitUntil(lambda: 0 < page.table.row_count() < 30, timeout=5000)
    assert all(a.vacc_status == "просрочена" for a in page.table.model._rows)
    page.search.setText("несуществующее-имя")
    qtbot.waitUntil(lambda: page.table.row_count() == 0, timeout=5000)
    assert page.table.stack.currentWidget() is page.table.empty
    page.reset_filters()
    qtbot.waitUntil(lambda: page.table.row_count() == 30, timeout=5000)


def test_t31_ui_new_appointment_cancel_does_not_save(qtbot, window, db_path):
    """T-31 | UI: диалог новой записи, отмена | заполнить поля, нажать Отмена | запись не создана."""
    conn = db.connect(db_path)
    before = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    dlg = AppointmentDialog(window.ctx, parent=window)
    qtbot.addWidget(dlg)
    dlg.show()
    dlg.phone.setText("+375292000037")  # владелец 1 из seed
    dlg.slots.setCurrentRow(0)
    dlg.reject()
    assert dlg.result() == QDialog.DialogCode.Rejected
    assert conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] == before


def test_t32_ui_new_appointment_flow(qtbot, window, db_path):
    """T-32 | UI: запись через диалог | телефон → животное → услуга (врачи фильтруются) → слот → OK |
    запись создана с ценой из прайса; врачи — только нужной специализации; кнопка OK неактивна до валидности."""
    conn = db.connect(db_path)
    owner = conn.execute("SELECT o.phone FROM owners o JOIN animals a ON a.owner_id = o.id LIMIT 1").fetchone()[0]
    dlg = AppointmentDialog(window.ctx, parent=window)
    qtbot.addWidget(dlg)
    dlg.show()
    ok_btn = dlg.buttons.button(dlg.buttons.StandardButton.Ok)
    assert not ok_btn.isEnabled()  # форма невалидна
    dlg.phone.setText(owner)
    assert dlg.animal.count() > 0 and dlg.owner_id is not None
    # услуга «Кастрация / стерилизация» -> только хирурги
    idx = next(i for i in range(dlg.service.count())
               if dlg.service.model().item(i).data(Qt.ItemDataRole.UserRole)
               and dlg.service.model().item(i).data(Qt.ItemDataRole.UserRole).name.startswith("Кастрация"))
    dlg.service.setCurrentIndex(idx)
    assert dlg.vet.count() >= 1 and all("Хирург" in dlg.vet.itemText(i) for i in range(dlg.vet.count()))
    assert dlg.price_label.text().startswith("200,00")
    dlg.date.setDate(QDate(2027, 3, 15))
    free = next(i for i in range(dlg.slots.count()) if dlg.slots.item(i).flags() & Qt.ItemFlag.ItemIsEnabled)
    dlg.slots.setCurrentRow(free)
    assert ok_btn.isEnabled()
    n = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    dlg.on_accept()
    assert conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] == n + 1
    row = conn.execute("SELECT price_kopecks, appt_date, status FROM appointments ORDER BY id DESC LIMIT 1").fetchone()
    assert tuple(row) == (20000, "2027-03-15", "запланирован")
    assert window.prepay_offers and window.prepay_offers[-1][1] == 20000  # предложена предоплата полной суммы


def test_t33_ui_close_visit_rollback_message(qtbot, window, db_path):
    """T-33 | UI: закрытие приёма при нехватке препарата | назначить 9999 ед. → «Закрыть» | понятное сообщение,
    статус записи не изменился, ничего не списано."""
    conn = db.connect(db_path)
    appt = next(a for a in appt_repo.list_appointments(conn)
                if a.status == "подтверждён" and a.paid_kopecks == 0 and a.appt_date <= TODAY)
    dlg = CloseVisitDialog(window.ctx, appt, window)
    qtbot.addWidget(dlg)
    dlg.show()
    dlg.add_row()
    dlg.table.cellWidget(0, 1).setText("1 мл")
    dlg.table.cellWidget(0, 3).setValue(9999)
    dlg.recalc()
    stock_before = [tuple(r) for r in conn.execute("SELECT id, qty FROM stock_batches ORDER BY id")]
    dlg.on_accept()
    assert window.messages and window.messages[-1][0] == "critical" and "Недостаточно" in window.messages[-1][1]
    assert "Traceback" not in window.messages[-1][1]
    assert appt_repo.get_appointment(conn, appt.id).status == "подтверждён"
    assert [tuple(r) for r in conn.execute("SELECT id, qty FROM stock_batches ORDER BY id")] == stock_before
    assert dlg.result() != QDialog.DialogCode.Accepted


def test_t34_ui_close_visit_success_creates_payment(qtbot, window, db_path):
    """T-34 | UI: успешное закрытие приёма | назначение 1 ед. → «Закрыть и начислить оплату» | статус «завершён»,
    платёж «ожидает», диалог закрыт."""
    conn = db.connect(db_path)
    appt = next(a for a in appt_repo.list_appointments(conn)
                if a.status == "подтверждён" and a.paid_kopecks == 0 and a.appt_date <= TODAY)
    dlg = CloseVisitDialog(window.ctx, appt, window)
    qtbot.addWidget(dlg)
    dlg.show()
    dlg.diagnosis.setText("Здоров")
    dlg.add_row()
    dlg.table.cellWidget(0, 1).setText("1 мл утром")
    dlg.recalc()
    dlg.on_accept()
    assert dlg.result() == QDialog.DialogCode.Accepted
    after = appt_repo.get_appointment(conn, appt.id)
    assert after.status == "завершён" and after.visit_id
    assert conn.execute("SELECT status FROM payments WHERE appointment_id = ?", (appt.id,)).fetchone()[0] == "ожидает"


def test_t35_ui_animal_card_tabs_and_chart(qtbot, window, db_path):
    """T-35 | UI: карточка животного | открыть карточку животного с приёмами | 7 вкладок, данные загружены, график веса построен."""
    conn = db.connect(db_path)
    aid = conn.execute("SELECT a.animal_id FROM vital_signs vs JOIN visits v ON v.id = vs.visit_id "
                       "JOIN appointments a ON a.id = v.appointment_id WHERE vs.weight_kg IS NOT NULL LIMIT 1").fetchone()[0]
    card = AnimalCard(window.ctx, aid, window)
    qtbot.addWidget(card)
    card.show()
    qtbot.waitUntil(lambda: card.t_appts.row_count() > 0, timeout=5000)
    assert card.tabs.count() == 7
    assert [card.tabs.tabText(i) for i in range(6)] == ["Владелец", "Приёмы", "Вакцинации", "Назначения", "Оплаты", "Заметки"]
    assert card.chart.stack.currentWidget() is card.chart.view
    assert len(card.chart.chart.series()) == 2


def test_t36_ui_report_runs_and_empty_result(qtbot, window):
    """T-36 | UI: отчёт и пустой результат | сформировать оперативный отчёт на дату без приёмов | метка «Данных нет»."""
    window.nav.setCurrentRow(8)
    page = window.pages["Отчёты"]
    page.op_date.setDate(QDate(2026, 10, 28))
    page.run_report()
    qtbot.waitUntil(lambda: page.result is not None, timeout=5000)
    assert not page.result.empty and page.result_stack.currentWidget() is page.table
    page.result = None
    page.op_date.setDate(QDate(2001, 1, 1))
    page.run_report()
    qtbot.waitUntil(lambda: page.result is not None, timeout=5000)
    assert page.result.empty and page.result_stack.currentWidget() is page.no_data


def test_t37_ui_status_buttons_follow_transitions(qtbot, window):
    """T-37 | UI: кнопки статусов зависят от допустимости перехода | выбрать завершённую запись | подтвердить/отменить/закрыть неактивны."""
    page = window.pages["Записи на приём"]
    window.nav.setCurrentRow(2)
    qtbot.waitUntil(lambda: page.table.row_count() > 0, timeout=5000)
    rows = page.table.model._rows
    done = next(i for i, a in enumerate(rows) if a.status == "завершён")
    page.table.view.selectRow(page.table.proxy.mapFromSource(page.table.model.index(done, 0)).row())
    assert not (page.b_confirm.isEnabled() or page.b_cancel.isEnabled() or page.b_close.isEnabled())
    planned = next(i for i, a in enumerate(rows) if a.status == "запланирован")
    page.table.view.selectRow(page.table.proxy.mapFromSource(page.table.model.index(planned, 0)).row())
    assert page.b_confirm.isEnabled() and page.b_cancel.isEnabled() and page.b_close.isEnabled()


def test_t33_owner_without_animal_can_get_animal_from_dialogs(qtbot, window, monkeypatch):
    """T-33 | Новый владелец без животных | создать владельца; из диалога записи добавить животное; из диалога животного
    создать владельца кнопкой | животное привязано к владельцу, запись можно оформить, замкнутого круга нет."""
    from app.ui.dialogs import appointment as appt_mod, simple as simple_mod
    from app.repositories import clients as repo
    conn = db.connect(window.ctx.db_path)
    oid = repo.create_owner(conn, "Новый Владелец Тестович", "+375 44 555-66-77")
    dlg = AppointmentDialog(window.ctx, parent=window)
    qtbot.addWidget(dlg)
    dlg.phone.setText("+375445556677")
    assert dlg.owner_id == oid and dlg.animal.count() == 0 and dlg.add_animal.isEnabled()

    class FakeAnimalDialog:
        created_id = None
        def __init__(self, ctx, owner_id=None, parent=None):
            assert owner_id == oid
            FakeAnimalDialog.created_id = repo.create_animal(db.connect(window.ctx.db_path), owner_id, "Рекс", "Собака")
        def exec(self):
            return True
    monkeypatch.setattr(appt_mod, "AnimalDialog", FakeAnimalDialog)
    dlg.on_add_animal()
    assert dlg.animal.count() == 1 and dlg.animal.currentData() == FakeAnimalDialog.created_id

    ad = simple_mod.AnimalDialog(window.ctx, parent=window)
    qtbot.addWidget(ad)
    before = ad.owner.count()
    monkeypatch.setattr(simple_mod, "OwnerDialog", type("FakeOwnerDialog", (), {
        "created_id": None,
        "__init__": lambda self, ctx, owner=None, phone="", parent=None: setattr(
            self, "created_id", repo.create_owner(db.connect(window.ctx.db_path), "Ещё Один", "+375 33 111-22-33")),
        "exec": lambda self: True}))
    ad.on_new_owner()
    assert ad.owner.count() == before + 1 and "Ещё Один" in ad.owner.currentText()


def test_t38_ui_prepayment_from_appointments(qtbot, window, db_path):
    """T-38 | UI: предоплата по записи до приёма | выбрать неоплаченную запланированную запись → «Принять оплату» →
    сумма = полная цена | платёж «оплачен», кнопка оплаты становится неактивной."""
    from app.ui.dialogs.simple import PaymentDialog
    page = window.pages["Записи на приём"]
    window.goto("Записи на приём")
    qtbot.waitUntil(lambda: page.table.row_count() > 0, timeout=5000)
    rows = page.table.model._rows
    i = next(i for i, a in enumerate(rows) if a.status == "запланирован" and a.paid_kopecks == 0)
    a = rows[i]
    page.table.view.selectRow(page.table.proxy.mapFromSource(page.table.model.index(i, 0)).row())
    assert page.b_pay.isEnabled()
    dlg = PaymentDialog(window.ctx, a.id, a.price_kopecks - a.paid_kopecks, page)
    qtbot.addWidget(dlg)
    dlg.on_accept()
    assert dlg.result() == QDialog.DialogCode.Accepted
    conn = db.connect(db_path)
    assert conn.execute("SELECT status, amount_kopecks FROM payments WHERE appointment_id=?", (a.id,)).fetchone()[:] \
        == ("оплачен", a.price_kopecks)
    assert appt_repo.get_appointment(conn, a.id).status == "запланирован"  # запись не закрыта — это предоплата


def test_t39_ui_dashboard_tiles_navigate_and_action_hint(qtbot, window):
    """T-39 | UI: плитки дашборда ведут в нужный список с фильтром; подсказка объясняет доступные действия |
    клик «Просроченных ревакцинаций» → «Животные» с флажком просрочки; «Приёмов на сегодня» → записи за дату."""
    window.dashboard.tiles["overdue"].clicked.emit()
    assert window.current_page() is window.pages["Животные"] and window.pages["Животные"].overdue.isChecked()
    window.dashboard.tiles["today"].clicked.emit()
    page = window.pages["Записи на приём"]
    assert window.current_page() is page
    assert page.d_from.date() == page.d_to.date() == QDate.fromString(TODAY, "yyyy-MM-dd")
    qtbot.waitUntil(lambda: page.table.row_count() > 0, timeout=5000)
    assert "Выберите запись" in page.action_hint.text()
    page.table.view.selectRow(0)
    assert "Выберите запись" not in page.action_hint.text()
    window.dashboard.tiles["unpaid"].clicked.emit()
    assert window.pages["Приёмы"].only_debt.isChecked()
