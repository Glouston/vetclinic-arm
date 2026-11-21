"""Справочники: врачи, услуги (с историей цен), препараты."""
from __future__ import annotations
import sqlite3
from datetime import date, timedelta

from app.db import transaction
from app.errors import UserError
from app.models import Medication, PriceVersion, Service, Vet
from app.util import normalize_phone, today_iso
from app.repositories.clients import _like


# --------------------------------------------------------------------- врачи
def list_vets(conn, only_active: bool = False, search: str | None = None) -> list[Vet]:
    rows = conn.execute(
        """SELECT id, full_name, specialization, phone, is_active FROM vets
           WHERE (:a = 0 OR is_active = 1)
             AND (:s IS NULL OR ulower(full_name) LIKE :s ESCAPE '\\' OR ulower(specialization) LIKE :s ESCAPE '\\')
           ORDER BY full_name""", {"a": 1 if only_active else 0, "s": _like(search)}).fetchall()
    return [Vet.from_row(r) for r in rows]


def vets_for_service(conn, service_id: int) -> list[Vet]:
    """Активные врачи, чья специализация подходит услуге (NULL в услуге — любой врач)."""
    rows = conn.execute(
        """SELECT v.id, v.full_name, v.specialization, v.phone, v.is_active
           FROM vets v JOIN services s ON s.id = ?
           WHERE v.is_active = 1
             AND (s.required_specialization IS NULL OR s.required_specialization = v.specialization)
           ORDER BY v.full_name""", (service_id,)).fetchall()
    return [Vet.from_row(r) for r in rows]


def list_specializations(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT specialization FROM vets ORDER BY 1")]


def save_vet(conn, vet_id: int | None, full_name: str, specialization: str, phone: str | None, is_active: bool) -> int:
    if not full_name.strip() or not specialization.strip():
        raise UserError("Укажите ФИО и специализацию врача.")
    phone = normalize_phone(phone) if phone and phone.strip() else None
    if vet_id is None:
        return conn.execute(
            "INSERT INTO vets (full_name, specialization, phone, is_active) VALUES (?, ?, ?, ?)",
            (full_name.strip(), specialization.strip(), phone or None, int(is_active))).lastrowid
    conn.execute("UPDATE vets SET full_name = ?, specialization = ?, phone = ?, is_active = ? WHERE id = ?",
                 (full_name.strip(), specialization.strip(), phone or None, int(is_active), vet_id))
    return vet_id


def delete_vet(conn, vet_id: int) -> None:
    n = conn.execute("SELECT COUNT(*) FROM appointments WHERE vet_id = ?", (vet_id,)).fetchone()[0]
    if n:
        raise UserError(f"Нельзя удалить врача: есть связанные записи на приём ({n}). "
                        "Снимите отметку «Работает», чтобы врач не выбирался в новых записях.")
    conn.execute("DELETE FROM vets WHERE id = ?", (vet_id,))


# -------------------------------------------------------------------- услуги
_SERVICE_SELECT = """
SELECT s.id, s.name, s.category, s.duration_min, s.required_specialization,
       (SELECT p.price_kopecks FROM service_prices p
         WHERE p.service_id = s.id AND p.valid_from <= :on AND (p.valid_to IS NULL OR p.valid_to >= :on)
         ORDER BY p.valid_from DESC LIMIT 1) AS price_kopecks
FROM services s
"""


def list_services(conn, on_date: str | None = None, search: str | None = None) -> list[Service]:
    rows = conn.execute(
        _SERVICE_SELECT + """ WHERE :s IS NULL OR ulower(s.name) LIKE :s ESCAPE '\\' OR ulower(s.category) LIKE :s ESCAPE '\\'
                              ORDER BY s.category, s.name""",
        {"on": on_date or today_iso(), "s": _like(search)}).fetchall()
    return [Service.from_row(r) for r in rows]


def get_service(conn, service_id: int, on_date: str | None = None) -> Service | None:
    r = conn.execute(_SERVICE_SELECT + " WHERE s.id = :id", {"on": on_date or today_iso(), "id": service_id}).fetchone()
    return Service.from_row(r) if r else None


def current_price(conn, service_id: int, on_date: str | None = None) -> int:
    """Актуальная цена услуги на дату — снимок для записи на приём."""
    s = get_service(conn, service_id, on_date)
    if s is None or s.price_kopecks is None:
        raise UserError("Для услуги не задана действующая цена.")
    return s.price_kopecks


def save_service(conn, service_id: int | None, name: str, category: str | None, duration_min: int | None,
                 required_specialization: str | None, first_price_kopecks: int | None = None) -> int:
    if not name.strip():
        raise UserError("Укажите название услуги.")
    with transaction(conn):
        if service_id is None:
            service_id = conn.execute(
                "INSERT INTO services (name, category, duration_min, required_specialization) VALUES (?, ?, ?, ?)",
                (name.strip(), category or None, duration_min or None, required_specialization or None)).lastrowid
            if first_price_kopecks is not None:
                conn.execute(
                    "INSERT INTO service_prices (service_id, price_kopecks, valid_from) VALUES (?, ?, ?)",
                    (service_id, first_price_kopecks, today_iso()))
        else:
            conn.execute(
                "UPDATE services SET name = ?, category = ?, duration_min = ?, required_specialization = ? WHERE id = ?",
                (name.strip(), category or None, duration_min or None, required_specialization or None, service_id))
    return service_id


def delete_service(conn, service_id: int) -> None:
    n = conn.execute("SELECT COUNT(*) FROM appointments WHERE service_id = ?", (service_id,)).fetchone()[0]
    if n:
        raise UserError(f"Нельзя удалить услугу: она использована в записях на приём ({n}).")
    with transaction(conn):
        conn.execute("DELETE FROM service_prices WHERE service_id = ?", (service_id,))
        conn.execute("DELETE FROM services WHERE id = ?", (service_id,))


def list_categories(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT category FROM services WHERE category IS NOT NULL ORDER BY 1")]


def price_history(conn, service_id: int) -> list[PriceVersion]:
    rows = conn.execute(
        "SELECT id, service_id, price_kopecks, valid_from, valid_to FROM service_prices "
        "WHERE service_id = ? ORDER BY valid_from DESC", (service_id,)).fetchall()
    return [PriceVersion.from_row(r) for r in rows]


def add_price_version(conn, service_id: int, price_kopecks: int, valid_from: str) -> None:
    """Новая версия цены; старая не редактируется, а закрывается днём раньше (ТЗ п.5.4)."""
    if price_kopecks < 0:
        raise UserError("Цена не может быть отрицательной.")
    try:
        date.fromisoformat(valid_from)
    except (TypeError, ValueError):
        raise UserError("Дата начала действия цены указана неверно.") from None
    with transaction(conn):
        last = conn.execute(
            "SELECT MAX(valid_from) FROM service_prices WHERE service_id = ?", (service_id,)).fetchone()[0]
        if last is not None and valid_from <= last:
            raise UserError("Дата начала новой цены должна быть позже начала действующей версии.")
        closing = (date.fromisoformat(valid_from) - timedelta(days=1)).isoformat()
        conn.execute("UPDATE service_prices SET valid_to = ? WHERE service_id = ? AND valid_to IS NULL",
                     (closing, service_id))
        conn.execute("INSERT INTO service_prices (service_id, price_kopecks, valid_from) VALUES (?, ?, ?)",
                     (service_id, price_kopecks, valid_from))


# ----------------------------------------------------------------- препараты
def list_medications(conn) -> list[Medication]:
    return [Medication.from_row(r) for r in conn.execute("SELECT id, name, unit FROM medications ORDER BY name")]


def create_medication(conn: sqlite3.Connection, name: str, unit: str) -> int:
    if not name.strip() or not unit.strip():
        raise UserError("Укажите название препарата и единицу измерения.")
    return conn.execute("INSERT INTO medications (name, unit) VALUES (?, ?)", (name.strip(), unit.strip())).lastrowid
