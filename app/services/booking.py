"""Запись на приём: создание с проверками и смена статусов."""
from __future__ import annotations
import sqlite3

from app.db import transaction
from app.errors import UserError
from app.repositories import appointments as appt_repo
from app.repositories import catalog
from app.services import payments
from app.util import today_iso

# допустимые переходы статуса записи (ТЗ 8.4)
TRANSITIONS = {
    "запланирован": {"подтверждён", "отменён", "завершён"},
    "подтверждён": {"отменён", "завершён"},
    "завершён": set(),
    "отменён": set(),
}


def can_transition(old: str, new: str) -> bool:
    return new in TRANSITIONS.get(old, set())


def create_appointment(conn: sqlite3.Connection, animal_id: int, vet_id: int, service_id: int,
                       appt_date: str, appt_time: str, today: str | None = None,
                       allow_past: bool = False) -> int:
    """Создаёт запись. Цена фиксируется из действующего прайса на момент записи."""
    today = today or today_iso()
    if appt_date < today and not allow_past:
        raise UserError("Дата записи не может быть в прошлом.")
    with transaction(conn):
        vet = conn.execute("SELECT specialization, is_active FROM vets WHERE id = ?", (vet_id,)).fetchone()
        service = conn.execute("SELECT required_specialization FROM services WHERE id = ?", (service_id,)).fetchone()
        if vet is None or service is None:
            raise UserError("Не найден врач или услуга.")
        if not vet["is_active"]:
            raise UserError("Этот врач сейчас не работает.")
        req = service["required_specialization"]
        if req and req != vet["specialization"]:
            raise UserError(f"Услугу оказывает только врач со специализацией «{req}».")
        if not appt_repo.slot_is_free(conn, vet_id, appt_date, appt_time):
            raise UserError("Это время у врача уже занято. Выберите другой слот.")
        price = catalog.current_price(conn, service_id, today)
        return conn.execute(
            """INSERT INTO appointments (animal_id, vet_id, service_id, appt_date, appt_time, status, price_kopecks)
               VALUES (?, ?, ?, ?, ?, 'запланирован', ?)""",
            (animal_id, vet_id, service_id, appt_date, appt_time, price)).lastrowid


def change_status(conn: sqlite3.Connection, appointment_id: int, new_status: str) -> None:
    """Подтвердить/отменить. «Завершён» ставится только закрытием приёма (services.visits)."""
    if new_status not in ("подтверждён", "отменён"):
        raise UserError("Этот статус устанавливается другим действием.")
    with transaction(conn):
        row = conn.execute("SELECT status FROM appointments WHERE id = ?", (appointment_id,)).fetchone()
        if row is None:
            raise UserError("Запись не найдена.")
        if not can_transition(row["status"], new_status):
            raise UserError(f"Недопустимый переход: «{row['status']}» → «{new_status}».")
        conn.execute("UPDATE appointments SET status = ? WHERE id = ?", (new_status, appointment_id))
        if new_status == "отменён":  # внесённая заранее оплата возвращается клиенту
            payments.refund_prepayment(conn, appointment_id)
