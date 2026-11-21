"""Склад: партии и журнал движений (только чтение; изменения — в services/stock_ops)."""
from __future__ import annotations
from app.models import Batch, Movement
from app.repositories.clients import _like
from app.util import today_iso


def list_batches(conn, today: str | None = None, within_days: int | None = None, search: str | None = None,
                 only_nonzero: bool = False) -> list[Batch]:
    """within_days: показать только партии, истекающие не позднее чем через N дней (и ещё не просроченные)."""
    rows = conn.execute(
        """SELECT b.id, b.medication_id, m.name AS medication_name, m.unit, b.batch_no, b.qty, b.expiry_date,
                  CASE WHEN b.expiry_date < :t THEN 'просрочен'
                       WHEN b.expiry_date <= date(:t, '+30 days') THEN 'истекает'
                       ELSE 'в норме' END AS state
           FROM stock_batches b JOIN medications m ON m.id = b.medication_id
           WHERE (:days IS NULL OR (b.expiry_date >= :t AND b.expiry_date <= date(:t, '+' || :days || ' days')))
             AND (:s IS NULL OR ulower(m.name) LIKE :s ESCAPE '\\' OR ulower(b.batch_no) LIKE :s ESCAPE '\\')
             AND (:nz = 0 OR b.qty > 0)
           ORDER BY m.name, b.expiry_date""",
        {"t": today or today_iso(), "days": within_days, "s": _like(search), "nz": int(only_nonzero)}).fetchall()
    return [Batch.from_row(r) for r in rows]


def available_qty(conn, medication_id: int, today: str | None = None) -> int:
    return conn.execute(
        "SELECT COALESCE(SUM(qty), 0) FROM stock_batches WHERE medication_id = ? AND expiry_date >= ?",
        (medication_id, today or today_iso())).fetchone()[0]


def list_movements(conn, batch_id: int | None = None, limit: int = 200) -> list[Movement]:
    rows = conn.execute(
        """SELECT sm.id, sm.moved_at, m.name AS medication_name, b.batch_no, sm.qty_delta, sm.reason
           FROM stock_movements sm JOIN stock_batches b ON b.id = sm.batch_id
           JOIN medications m ON m.id = b.medication_id
           WHERE (:b IS NULL OR sm.batch_id = :b)
           ORDER BY sm.moved_at DESC, sm.id DESC LIMIT :n""", {"b": batch_id, "n": limit}).fetchall()
    return [Movement.from_row(r) for r in rows]
