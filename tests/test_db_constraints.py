"""Негативные тесты целостности: FK, CHECK, UNIQUE, NOT NULL, триггеры, удаление, развёртывание.

Формат: ID | проверяемое требование | шаги | ожидаемый результат (фактический — результат прогона pytest).
"""
from __future__ import annotations
import sqlite3

import pytest

from app import db
from app.errors import DatabaseUnavailable, UserError, to_user_message
from app.repositories import clients


def test_t01_deploy_from_scripts(tmp_path):
    """T-01 | Развёртывание из schema.sql+seed.sql | создать пустой файл, init_db |
    ≥50 приёмов, 15 таблиц, повторный init_db данные не стирает."""
    path = tmp_path / "x.db"
    assert db.init_db(path) is True
    c = db.connect(path)
    assert c.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] >= 50
    tables = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
    assert tables == 15
    c.execute("DELETE FROM reminders")
    assert db.init_db(path) is False  # БД не пуста — ничего не пересоздаётся
    assert c.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] >= 50


def test_t02_foreign_keys_enabled(conn):
    """T-02 | PRAGMA foreign_keys=ON в каждом соединении | connect() | значение 1."""
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_t03_unique_phone(conn):
    """T-03 | UNIQUE телефона владельца | создать владельца с занятым телефоном | IntegrityError + понятный текст."""
    phone = conn.execute("SELECT phone FROM owners LIMIT 1").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError) as e:
        conn.execute("INSERT INTO owners (full_name, phone) VALUES ('Дубль', ?)", (phone,))
    assert "телефоном" in to_user_message(e.value)


def test_t04_not_null_required_field(conn):
    """T-04 | Пропуск обязательного поля | animals без name | отказ, строка не добавлена."""
    before = conn.execute("SELECT COUNT(*) FROM animals").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO animals (owner_id, species) VALUES (1, 'Кот')")
    with pytest.raises(UserError):
        clients.create_animal(conn, 1, "  ", "Кот")
    assert conn.execute("SELECT COUNT(*) FROM animals").fetchone()[0] == before


@pytest.mark.parametrize("sql", [
    "INSERT INTO animals (owner_id, name, species, sex) VALUES (1, 'А', 'Кот', 'X')",
    "INSERT INTO animals (owner_id, name, species, birth_date) VALUES (1, 'А', 'Кот', '2020-13-45')",
    "INSERT INTO service_prices (service_id, price_kopecks, valid_from) VALUES (2, -5, '2030-01-01')",
    "INSERT INTO stock_batches (medication_id, batch_no, qty, expiry_date) VALUES (4, 'NEW', -1, '2030-01-01')",
    "INSERT INTO owners (full_name, phone) VALUES ('Х', '123')",
])
def test_t05_check_constraints(conn, sql):
    """T-05 | CHECK: пол, формат даты, цена >=0, остаток >=0, формат телефона | недопустимое значение | IntegrityError."""
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql)


def test_t06_check_vital_ranges(conn):
    """T-06 | CHECK температура 35..43, вес >0 | вставка 50 °C / вес 0 | отказ."""
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO vital_signs (visit_id, temp_c) VALUES (1, 50)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO vital_signs (visit_id, weight_kg) VALUES (1, 0)")


def test_t07_foreign_key_missing_parent(conn):
    """T-07 | FK на несуществующую запись | животное с owner_id=9999 | IntegrityError FOREIGN KEY."""
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute("INSERT INTO animals (owner_id, name, species) VALUES (9999, 'Х', 'Кот')")


def test_t08_unique_slot_and_cancelled_slot_reuse(conn):
    """T-08 | UNIQUE слота врача среди активных записей | две записи на одно время; затем после отмены | дубль — отказ, после отмены слот свободен."""
    conn.execute("INSERT INTO appointments (animal_id, vet_id, service_id, appt_date, appt_time, price_kopecks) "
                 "VALUES (1, 1, 2, '2030-05-05', '10:00', 100)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO appointments (animal_id, vet_id, service_id, appt_date, appt_time, price_kopecks) "
                     "VALUES (2, 1, 2, '2030-05-05', '10:00', 100)")
    conn.execute("UPDATE appointments SET status='отменён' WHERE appt_date='2030-05-05'")
    conn.execute("INSERT INTO appointments (animal_id, vet_id, service_id, appt_date, appt_time, price_kopecks) "
                 "VALUES (2, 1, 2, '2030-05-05', '10:00', 100)")


def test_t09_specialization_trigger(conn):
    """T-09 | Врач не той специализации | хирургическая услуга (8) у терапевта (1) | ошибка триггера."""
    with pytest.raises(sqlite3.IntegrityError, match="Специализация"):
        conn.execute("INSERT INTO appointments (animal_id, vet_id, service_id, appt_date, appt_time, price_kopecks) "
                     "VALUES (1, 1, 8, '2030-05-06', '10:00', 100)")


def test_t10_delete_forbidden_and_allowed(conn):
    """T-10 | Удаление: владельца с животными и животного с историей — нельзя; без истории — можно |
    delete_owner/delete_animal | отказ с понятным текстом; разрешённое удаляется (каскадом вакцинации)."""
    with pytest.raises(UserError, match="животных"):
        clients.delete_owner(conn, 1)
    animal_with_history = conn.execute("SELECT animal_id FROM appointments LIMIT 1").fetchone()[0]
    with pytest.raises(UserError, match="история приёмов"):
        clients.delete_animal(conn, animal_with_history)
    with pytest.raises(sqlite3.IntegrityError):  # и на уровне БД (RESTRICT)
        conn.execute("DELETE FROM animals WHERE id = ?", (animal_with_history,))
    clients.delete_animal(conn, 30)  # животное без приёмов
    assert clients.get_animal(conn, 30) is None
    clients.delete_owner(conn, 20)  # владелец без животных
    assert clients.get_owner(conn, 20) is None


def test_t11_payment_over_price_trigger(conn):
    """T-11 | Нельзя оплатить больше суммы приёма | платёж > цены на приёме с долгом | ошибка триггера."""
    visit = conn.execute("SELECT appointment_id, price_kopecks FROM v_debt_visits LIMIT 1").fetchone()
    with pytest.raises(sqlite3.IntegrityError, match="превышает"):
        conn.execute("INSERT INTO payments (appointment_id, amount_kopecks, method, status, paid_at) "
                     "VALUES (?, ?, 'карта', 'оплачен', '2026-10-28 10:00:00')",
                     (visit["appointment_id"], visit["price_kopecks"] + 100))


def test_t11b_payment_on_cancelled_trigger(conn):
    """T-11b | По отменённой записи нельзя принять оплату (только возврат) | INSERT «оплачен» | ошибка триггера."""
    cancelled = conn.execute("SELECT id FROM appointments WHERE status='отменён' LIMIT 1").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError, match="отменена"):
        conn.execute("INSERT INTO payments (appointment_id, amount_kopecks, method, status, paid_at) "
                     "VALUES (?, 100, 'карта', 'оплачен', '2026-10-28 10:00:00')", (cancelled,))


def test_t11c_invalid_calendar_date_rejected(conn):
    """T-11c | Несуществующая дата (30 февраля) | INSERT партии с expiry_date='2027-02-30' | CHECK отклоняет."""
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute("INSERT INTO stock_batches (medication_id, batch_no, qty, expiry_date) VALUES (1, 'Z-1', 1, '2027-02-30')")


def test_t12_status_flow_trigger(conn):
    """T-12 | Завершённую запись нельзя вернуть в «запланирован» | UPDATE status | ошибка триггера."""
    done = conn.execute("SELECT id FROM appointments WHERE status='завершён' LIMIT 1").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError, match="переход"):
        conn.execute("UPDATE appointments SET status='запланирован' WHERE id=?", (done,))


def test_t13_database_unavailable_and_recovery(tmp_path):
    """T-13 | Недоступность БД и восстановление | путь в несуществующей папке, затем создание папки |
    DatabaseUnavailable, после исправления соединение работает."""
    bad = tmp_path / "нет_папки" / "vet.db"
    with pytest.raises(DatabaseUnavailable):
        db.connect(bad)
    bad.parent.mkdir()
    db.init_db(bad)
    c = db.connect(bad)
    assert c.execute("SELECT COUNT(*) FROM owners").fetchone()[0] > 0
