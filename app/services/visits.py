"""Закрытие приёма — одна транзакция BEGIN IMMEDIATE (ТЗ п.6.3): всё или ничего."""
from __future__ import annotations
import sqlite3

from app.db import transaction
from app.errors import InsufficientStock, UserError
from app.models import PrescriptionInput
from app.util import now_str, today_iso


def deduct_fifo(conn: sqlite3.Connection, medication_id: int, qty: int, visit_id: int | None,
                reason: str, today: str, moved_at: str) -> None:
    """Списание по FIFO (раньше истекающие партии первыми), только непросроченные.

    Каждое списание — атомарный UPDATE … WHERE qty >= ?; rowcount == 0 -> InsufficientStock.
    Вызывать внутри транзакции: при исключении откатывается всё.
    """
    name = conn.execute("SELECT name FROM medications WHERE id = ?", (medication_id,)).fetchone()
    if name is None:
        raise UserError("Препарат не найден.")
    batches = conn.execute(
        """SELECT id, qty FROM stock_batches
           WHERE medication_id = ? AND qty > 0 AND expiry_date >= ?
           ORDER BY expiry_date, id""", (medication_id, today)).fetchall()
    available = sum(b["qty"] for b in batches)
    left = qty
    for b in batches:
        take = min(left, b["qty"])
        cur = conn.execute("UPDATE stock_batches SET qty = qty - ? WHERE id = ? AND qty >= ?",
                           (take, b["id"], take))
        if cur.rowcount == 0:
            raise InsufficientStock(f"Недостаточно препарата «{name['name']}» на складе.")
        conn.execute(
            "INSERT INTO stock_movements (batch_id, visit_id, qty_delta, reason, moved_at) VALUES (?, ?, ?, ?, ?)",
            (b["id"], visit_id, -take, reason, moved_at))
        left -= take
        if left == 0:
            return
    raise InsufficientStock(
        f"Недостаточно препарата «{name['name']}» на складе: нужно {qty}, доступно {available}. "
        "Приём не закрыт, изменения отменены.")


def close_appointment(conn: sqlite3.Connection, appointment_id: int, diagnosis: str | None, complaints: str | None,
                      prescriptions: list[PrescriptionInput], weight_kg: float | None = None,
                      temp_c: float | None = None, today: str | None = None, now: str | None = None,
                      allow_future: bool = False) -> int:
    """(a) статус «завершён» (b) visit (c) FIFO-списание (d) движения (e) платёж «ожидает» на неоплаченный остаток. Возвращает visit_id.

    Приём, назначенный на будущую дату, закрывается только с явным подтверждением (allow_future=True).
    """
    today = today or today_iso()
    now = now or now_str()
    with transaction(conn):
        appt = conn.execute("SELECT status, price_kopecks, appt_date FROM appointments WHERE id = ?",
                            (appointment_id,)).fetchone()
        if appt is None:
            raise UserError("Запись не найдена.")
        if appt["status"] not in ("запланирован", "подтверждён"):
            raise UserError(f"Приём со статусом «{appt['status']}» закрыть нельзя.")
        if appt["appt_date"] > today and not allow_future:
            raise UserError("Приём назначен на будущую дату — закрыть его можно только в день приёма или позже.")
        conn.execute("UPDATE appointments SET status = 'завершён' WHERE id = ?", (appointment_id,))
        visit_id = conn.execute(
            "INSERT INTO visits (appointment_id, diagnosis, complaints, closed_at) VALUES (?, ?, ?, ?)",
            (appointment_id, (diagnosis or "").strip() or None, (complaints or "").strip() or None, now)).lastrowid
        for p in prescriptions:
            conn.execute(
                "INSERT INTO prescriptions (visit_id, medication_id, dosage, course_days, qty) VALUES (?, ?, ?, ?, ?)",
                (visit_id, p.medication_id, p.dosage, p.course_days, p.qty))
            deduct_fifo(conn, p.medication_id, p.qty, visit_id, "Списание по назначению", today, now)
        if weight_kg is not None or temp_c is not None:
            conn.execute("INSERT INTO vital_signs (visit_id, weight_kg, temp_c, measured_at) VALUES (?, ?, ?, ?)",
                         (visit_id, weight_kg, temp_c, now))
        # (e) начисление «ожидает» — только на остаток, не покрытый предоплатой
        paid = conn.execute(
            """SELECT COALESCE(SUM(CASE status WHEN 'оплачен' THEN amount_kopecks
                                               WHEN 'возврат' THEN -amount_kopecks ELSE 0 END), 0)
               FROM payments WHERE appointment_id = ?""", (appointment_id,)).fetchone()[0]
        if appt["price_kopecks"] - paid > 0:
            conn.execute("INSERT INTO payments (appointment_id, amount_kopecks, status) VALUES (?, ?, 'ожидает')",
                         (appointment_id, appt["price_kopecks"] - paid))
    return visit_id
