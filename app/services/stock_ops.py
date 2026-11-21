"""Операции склада: приход и списание (с причиной). Каждая — транзакция + запись в журнал движений."""
from __future__ import annotations
import sqlite3

from app.db import transaction
from app.errors import InsufficientStock, UserError
from app.util import now_str, today_iso


def receive(conn: sqlite3.Connection, medication_id: int, batch_no: str, qty: int, expiry_date: str,
            now: str | None = None, today: str | None = None) -> int:
    """Приход: новая партия или пополнение существующей (тот же препарат и серия)."""
    if expiry_date < (today or today_iso()):
        raise UserError("Нельзя оприходовать партию с истёкшим сроком годности.")
    if qty <= 0:
        raise UserError("Количество должно быть больше нуля.")
    if not batch_no.strip():
        raise UserError("Укажите серию партии.")
    now = now or now_str()
    with transaction(conn):
        row = conn.execute("SELECT id, expiry_date FROM stock_batches WHERE medication_id = ? AND batch_no = ?",
                           (medication_id, batch_no.strip())).fetchone()
        if row:
            if row["expiry_date"] != expiry_date:
                raise UserError("Серия уже есть на складе с другим сроком годности.")
            batch_id = row["id"]
            conn.execute("UPDATE stock_batches SET qty = qty + ? WHERE id = ?", (qty, batch_id))
        else:
            batch_id = conn.execute(
                "INSERT INTO stock_batches (medication_id, batch_no, qty, expiry_date) VALUES (?, ?, ?, ?)",
                (medication_id, batch_no.strip(), qty, expiry_date)).lastrowid
        conn.execute("INSERT INTO stock_movements (batch_id, qty_delta, reason, moved_at) VALUES (?, ?, ?, ?)",
                     (batch_id, qty, "Приход", now))
    return batch_id


def write_off(conn: sqlite3.Connection, batch_id: int, qty: int, reason: str, now: str | None = None) -> None:
    """Списание из конкретной партии. Атомарный UPDATE … qty >= ?; при нехватке — ROLLBACK и ошибка."""
    if qty <= 0:
        raise UserError("Количество должно быть больше нуля.")
    if not reason.strip():
        raise UserError("Укажите причину списания.")
    now = now or now_str()
    with transaction(conn):
        cur = conn.execute("UPDATE stock_batches SET qty = qty - ? WHERE id = ? AND qty >= ?", (qty, batch_id, qty))
        if cur.rowcount == 0:
            have = conn.execute("SELECT qty FROM stock_batches WHERE id = ?", (batch_id,)).fetchone()
            if have is None:
                raise UserError("Партия не найдена.")
            raise InsufficientStock(f"Нельзя списать {qty}: в партии осталось только {have['qty']}.")
        conn.execute("INSERT INTO stock_movements (batch_id, qty_delta, reason, moved_at) VALUES (?, ?, ?, ?)",
                     (batch_id, -qty, f"Списание: {reason.strip()}", now))
