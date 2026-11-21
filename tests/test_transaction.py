"""Бизнес-процесс и транзакции: полный цикл, COMMIT, ROLLBACK, сохранение после перезапуска, поиск/фильтры."""
from __future__ import annotations
import pytest

from app import db
from app.errors import InsufficientStock, UserError
from app.models import PrescriptionInput
from app.repositories import appointments as appt_repo
from app.repositories import clients, stock
from app.services import booking, payments, stock_ops, visits
from tests.conftest import TODAY


def _snapshot(conn):
    return {
        "appts": conn.execute("SELECT id, status FROM appointments ORDER BY id").fetchall(),
        "visits": conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0],
        "payments": conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0],
        "moves": conn.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0],
        "stock": [tuple(r) for r in conn.execute("SELECT id, qty FROM stock_batches ORDER BY id")],
    }


def test_t14_full_workflow(conn):
    """T-14 | Полный процесс: владелец → животное → запись → подтверждение → закрытие → оплата |
    после закрытия: статус «завершён», visit, списание, платёж «ожидает»; после оплаты долга нет."""
    oid = clients.create_owner(conn, "Тестов Тест Тестович", "8 029 111-22-33")
    aid = clients.create_animal(conn, oid, "Тузик", "Собака", sex="M")
    appt = booking.create_appointment(conn, aid, 1, 2, "2026-11-30", "12:00", today=TODAY)
    row = appt_repo.get_appointment(conn, appt)
    assert row.status == "запланирован" and row.price_kopecks == 2500  # цена зафиксирована из прайса
    booking.change_status(conn, appt, "подтверждён")
    before_qty = stock.available_qty(conn, 4, TODAY)
    with pytest.raises(UserError, match="будущую дату"):  # без подтверждения будущий приём не закрывается
        visits.close_appointment(conn, appt, "Здоров", "", [], today=TODAY)
    vid = visits.close_appointment(conn, appt, "Здоров", "Осмотр", [PrescriptionInput(4, "1 мл 2 р/д", 5, 3)],
                                   weight_kg=12.5, temp_c=38.4, today=TODAY, now=f"{TODAY} 12:30:00",
                                   allow_future=True)
    assert appt_repo.get_appointment(conn, appt).status == "завершён"
    assert stock.available_qty(conn, 4, TODAY) == before_qty - 3
    assert conn.execute("SELECT status, amount_kopecks FROM payments WHERE appointment_id=?", (appt,)).fetchone()[:] == ("ожидает", 2500)
    assert conn.execute("SELECT closed_at FROM visits WHERE id=?", (vid,)).fetchone()[0]
    payments.accept_payment(conn, appt, 2500, "карта")
    assert conn.execute("SELECT COUNT(*) FROM v_debt_visits WHERE visit_id=?", (vid,)).fetchone()[0] == 0


def test_t15_commit_and_persist_after_restart(db_path):
    """T-15 | Сохранение после перезапуска | изменить владельца, закрыть соединение, открыть заново | данные на месте."""
    c1 = db.connect(db_path)
    clients.update_owner(c1, 1, "Новое Имя Иванович", "+375290000001", "Новый адрес", None)
    c1.close()
    c2 = db.connect(db_path)
    o = clients.get_owner(c2, 1)
    assert o.full_name == "Новое Имя Иванович" and o.address == "Новый адрес"


def test_t16_rollback_on_insufficient_stock(conn):
    """T-16 | Откат при нехватке препарата | закрыть приём с назначением 1000 ед. | InsufficientStock,
    состояние БД (статусы, visits, payments, остатки, движения) до и после — идентично."""
    appt = next(a for a in appt_repo.list_appointments(conn) if a.status in ("запланирован", "подтверждён"))
    before = _snapshot(conn)
    with pytest.raises(InsufficientStock, match="Недостаточно"):
        visits.close_appointment(
            conn, appt.id, "Тест", None,
            [PrescriptionInput(4, "1 мл", 3, 1), PrescriptionInput(5, "1 мл", 3, 1000)], today=TODAY)
    assert _snapshot(conn) == before  # первое назначение тоже откатилось
    assert appt_repo.get_appointment(conn, appt.id).status == appt.status


def test_t17_fifo_deduction(conn):
    """T-17 | FIFO: сначала партия с ранним сроком, просроченные не списываются | списать больше остатка первой партии |
    первая партия обнулена, остаток взят из следующей, просроченная партия не тронута."""
    expired = conn.execute("SELECT id, qty FROM stock_batches WHERE expiry_date < ?", (TODAY,)).fetchone()
    with db.transaction(conn):
        visits.deduct_fifo(conn, 7, 50, None, "тест", TODAY, f"{TODAY} 10:00:00")
    left = [tuple(r) for r in conn.execute(
        "SELECT batch_no, qty FROM stock_batches WHERE medication_id = 7 ORDER BY expiry_date")]
    assert left[0][1] == 0  # CFT-2406 (раньше истекает) выбрана полностью
    assert sum(q for _, q in left) == stock.available_qty(conn, 7, TODAY)
    assert conn.execute("SELECT qty FROM stock_batches WHERE id=?", (expired["id"],)).fetchone()[0] == expired["qty"]


def test_t18_write_off_atomic(conn):
    """T-18 | Нельзя списать больше остатка партии | write_off(qty > остатка) | InsufficientStock, остаток и журнал не изменились."""
    b = conn.execute("SELECT id, qty FROM stock_batches WHERE qty > 0 LIMIT 1").fetchone()
    moves = conn.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0]
    with pytest.raises(InsufficientStock):
        stock_ops.write_off(conn, b["id"], b["qty"] + 1, "брак")
    with pytest.raises(UserError):
        stock_ops.write_off(conn, b["id"], 1, " ")  # причина обязательна
    assert conn.execute("SELECT qty FROM stock_batches WHERE id=?", (b["id"],)).fetchone()[0] == b["qty"]
    assert conn.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0] == moves
    stock_ops.write_off(conn, b["id"], 1, "брак")
    assert conn.execute("SELECT qty FROM stock_batches WHERE id=?", (b["id"],)).fetchone()[0] == b["qty"] - 1


def test_t19_booking_rules(conn):
    """T-19 | Правила записи: специализация, занятый слот, прошлая дата, переходы статуса |
    каждое нарушение даёт UserError, запись не создаётся."""
    n = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    with pytest.raises(UserError, match="специализац"):
        booking.create_appointment(conn, 1, 1, 8, "2030-01-10", "10:00", today=TODAY)
    booking.create_appointment(conn, 1, 1, 2, "2030-01-10", "10:00", today=TODAY)
    with pytest.raises(UserError, match="занято"):
        booking.create_appointment(conn, 2, 1, 2, "2030-01-10", "10:00", today=TODAY)
    with pytest.raises(UserError, match="прошлом"):
        booking.create_appointment(conn, 1, 1, 2, "2020-01-10", "11:00", today=TODAY)
    assert conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] == n + 1
    done = conn.execute("SELECT id FROM appointments WHERE status='завершён' LIMIT 1").fetchone()[0]
    with pytest.raises(UserError, match="Недопустимый переход"):
        booking.change_status(conn, done, "отменён")


def test_t20_payment_limit_service(conn):
    """T-20 | Нельзя оплатить больше суммы приёма (сервис) | accept_payment(долг+1 коп.) | UserError; частичная оплата уменьшает долг."""
    d = conn.execute("SELECT visit_id, appointment_id, debt_kopecks FROM v_debt_visits WHERE paid_kopecks = 0 LIMIT 1").fetchone()
    with pytest.raises(UserError, match="больше суммы"):
        payments.accept_payment(conn, d["appointment_id"], d["debt_kopecks"] + 1, "наличные")
    payments.accept_payment(conn, d["appointment_id"], 100, "наличные")
    debt = conn.execute("SELECT debt_kopecks FROM v_debt_visits WHERE visit_id=?", (d["visit_id"],)).fetchone()[0]
    assert debt == d["debt_kopecks"] - 100


def test_t21_search_filters_sort_empty(conn):
    """T-21 | Поиск, совместные фильтры, сортировка, пустой результат |
    фильтры вид+пол+просрочка применяются вместе (AND); несуществующий поиск — пусто."""
    dogs = clients.list_animals(conn, species="Собака", today=TODAY)
    assert dogs and all(a.species == "Собака" for a in dogs)
    both = clients.list_animals(conn, species="Собака", sex="F", only_overdue=True, today=TODAY)
    assert all(a.species == "Собака" and a.sex == "F" and a.vacc_status == "просрочена" for a in both)
    assert len(both) <= len(dogs)
    assert clients.list_animals(conn, search="ZZZ-нет-такого", today=TODAY) == []
    by_phone = clients.list_animals(conn, search="+37529", today=TODAY)
    assert by_phone
    listed = appt_repo.list_appointments(conn, date_from="2026-10-01", date_to="2026-10-31", status="завершён")
    assert all("2026-10-01" <= a.appt_date <= "2026-10-31" and a.status == "завершён" for a in listed)
    assert [a.appt_date for a in listed] == sorted(a.appt_date for a in listed)


def test_t20b_prepayment_then_close_and_cancel_refund(conn):
    """T-20b | Предоплата: оплата сразу при записи / при отмене — возврат |
    запись → оплата 100% → закрытие: «ожидает» не начисляется, долга нет;
    запись → частичная предоплата → отмена: автоматически оформлен «возврат», оплачено 0."""
    appt = booking.create_appointment(conn, 1, 1, 2, TODAY, "18:30", today=TODAY)
    payments.accept_payment(conn, appt, 2500, "карта", now=f"{TODAY} 09:00:00")
    with pytest.raises(UserError, match="уже оплачен"):
        payments.accept_payment(conn, appt, 1, "карта")
    vid = visits.close_appointment(conn, appt, "Здоров", "", [], today=TODAY)
    assert conn.execute("SELECT COUNT(*) FROM payments WHERE appointment_id=? AND status='ожидает'", (appt,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM v_debt_visits WHERE visit_id=?", (vid,)).fetchone()[0] == 0

    appt2 = booking.create_appointment(conn, 1, 1, 2, "2026-11-30", "10:00", today=TODAY)
    payments.accept_payment(conn, appt2, 1000, "наличные")
    vid2 = None
    booking.change_status(conn, appt2, "отменён")
    rows = conn.execute("SELECT status, amount_kopecks FROM payments WHERE appointment_id=? ORDER BY id", (appt2,)).fetchall()
    assert [tuple(r) for r in rows] == [("оплачен", 1000), ("возврат", 1000)]
    assert payments.balance(conn, appt2)[1] == 0
    with pytest.raises(UserError, match="отменена"):
        payments.accept_payment(conn, appt2, 100, "карта")
    assert vid2 is None


def test_t20c_partial_prepayment_close_charges_remainder(conn):
    """T-20c | Частичная предоплата | 1000 из 2500 при записи → закрытие | начислено «ожидает» 1500; доплата закрывает долг."""
    appt = booking.create_appointment(conn, 1, 1, 2, TODAY, "18:30", today=TODAY)
    payments.accept_payment(conn, appt, 1000, "карта")
    visits.close_appointment(conn, appt, "", "", [], today=TODAY)
    assert conn.execute("SELECT amount_kopecks FROM payments WHERE appointment_id=? AND status='ожидает'",
                        (appt,)).fetchone()[0] == 1500
    payments.accept_payment(conn, appt, 1500, "наличные")
    assert payments.balance(conn, appt)[:2] == (2500, 2500)


def test_t20d_cyrillic_search_case_insensitive(conn):
    """T-20d | Поиск без учёта регистра по кириллице | «барсик», «БАРСИК» | находится «Барсик»."""
    name = conn.execute("SELECT name FROM animals WHERE name GLOB '[А-Я]*' LIMIT 1").fetchone()[0]
    for q in (name.lower(), name.upper()):
        assert any(a.name == name for a in clients.list_animals(conn, search=q, today=TODAY))
