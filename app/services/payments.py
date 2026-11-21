"""Оплата по записи на приём с проверкой суммы внутри транзакции.

Оплатить можно в любой момент: сразу при записи (предоплата, полностью или частично)
или в день приёма / после него. При закрытии приёма на неоплаченный остаток начисляется
платёж «ожидает»; при отмене записи внесённая предоплата оформляется возвратом.
"""
from __future__ import annotations
import sqlite3

from app.db import transaction
from app.errors import UserError
from app.util import now_str

METHODS = ("наличные", "карта", "перевод")

PAID_SQL = """COALESCE((SELECT SUM(CASE status WHEN 'оплачен' THEN amount_kopecks
                                         WHEN 'возврат' THEN -amount_kopecks ELSE 0 END)
                  FROM payments WHERE appointment_id = a.id), 0)"""


def balance(conn: sqlite3.Connection, appointment_id: int) -> tuple[int, int, str]:
    """(цена записи, фактически оплачено, статус записи) — копейки."""
    r = conn.execute(f"SELECT a.price_kopecks, {PAID_SQL}, a.status FROM appointments a WHERE a.id = ?",
                     (appointment_id,)).fetchone()
    if r is None:
        raise UserError("Запись на приём не найдена.")
    return r[0], r[1], r[2]


def accept_payment(conn: sqlite3.Connection, appointment_id: int, amount_kopecks: int, method: str,
                   now: str | None = None) -> None:
    """Принимает оплату (полную или частичную, заранее или после приёма). Нельзя оплатить больше долга."""
    if method not in METHODS:
        raise UserError("Выберите способ оплаты.")
    if amount_kopecks <= 0:
        raise UserError("Сумма оплаты должна быть больше нуля.")
    now = now or now_str()
    with transaction(conn):
        price, paid, status = balance(conn, appointment_id)
        if status == "отменён":
            raise UserError("Запись отменена — принять оплату нельзя.")
        if price - paid <= 0:
            raise UserError("Приём уже оплачен полностью.")
        if amount_kopecks > price - paid:
            raise UserError("Нельзя оплатить больше суммы приёма.")
        # начисление «ожидает» (появляется при закрытии приёма) уменьшается на внесённую сумму
        pending = conn.execute(
            "SELECT id, amount_kopecks FROM payments WHERE appointment_id = ? AND status = 'ожидает' "
            "ORDER BY id LIMIT 1", (appointment_id,)).fetchone()
        if pending and pending["amount_kopecks"] == amount_kopecks:
            conn.execute("UPDATE payments SET status = 'оплачен', method = ?, paid_at = ? WHERE id = ?",
                         (method, now, pending["id"]))
            return
        if pending and pending["amount_kopecks"] > amount_kopecks:
            conn.execute("UPDATE payments SET amount_kopecks = amount_kopecks - ? WHERE id = ?",
                         (amount_kopecks, pending["id"]))
        elif pending:  # оплата больше начисления, но не больше долга
            conn.execute("DELETE FROM payments WHERE id = ?", (pending["id"],))
        conn.execute(
            "INSERT INTO payments (appointment_id, amount_kopecks, method, status, paid_at) "
            "VALUES (?, ?, ?, 'оплачен', ?)", (appointment_id, amount_kopecks, method, now))


def refund_prepayment(conn: sqlite3.Connection, appointment_id: int, now: str | None = None) -> int:
    """Возврат всей внесённой суммы по записи (вызывается внутри транзакции отмены). Возвращает сумму."""
    price, paid, _ = balance(conn, appointment_id)
    if paid <= 0:
        return 0
    method = conn.execute(
        "SELECT method FROM payments WHERE appointment_id = ? AND status = 'оплачен' ORDER BY id DESC LIMIT 1",
        (appointment_id,)).fetchone()
    conn.execute(
        "INSERT INTO payments (appointment_id, amount_kopecks, method, status, paid_at) VALUES (?, ?, ?, 'возврат', ?)",
        (appointment_id, paid, method["method"] if method else None, now or now_str()))
    return paid
