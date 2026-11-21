"""Проведённые приёмы: список для раздела «Приёмы» и данные для печатных форм."""
from __future__ import annotations
from app.models import VisitRow
from app.repositories.clients import _like


def list_visits(conn, search: str | None = None, only_debt: bool = False) -> list[VisitRow]:
    rows = conn.execute(
        """SELECT * FROM (
             SELECT vi.id AS visit_id, a.id AS appointment_id, a.appt_date, an.name AS animal_name,
                    o.full_name AS owner_name, v.full_name AS vet_name, s.name AS service_name, vi.diagnosis,
                    a.price_kopecks,
                    COALESCE((SELECT SUM(CASE p.status WHEN 'оплачен' THEN p.amount_kopecks
                                                       WHEN 'возврат' THEN -p.amount_kopecks ELSE 0 END)
                              FROM payments p WHERE p.appointment_id = a.id), 0) AS paid_kopecks
             FROM visits vi JOIN appointments a ON a.id = vi.appointment_id
             JOIN animals an ON an.id = a.animal_id JOIN owners o ON o.id = an.owner_id
             JOIN vets v ON v.id = a.vet_id JOIN services s ON s.id = a.service_id
             WHERE :s IS NULL OR ulower(an.name) LIKE :s ESCAPE '\\' OR ulower(o.full_name) LIKE :s ESCAPE '\\'
           ) t
           WHERE :debt = 0 OR price_kopecks - paid_kopecks > 0
           ORDER BY appt_date DESC, visit_id DESC""",
        {"s": _like(search), "debt": int(only_debt)}).fetchall()
    return [VisitRow(r["visit_id"], r["appointment_id"], r["appt_date"], r["animal_name"], r["owner_name"],
                     r["vet_name"], r["service_name"], r["diagnosis"], r["price_kopecks"], r["paid_kopecks"],
                     r["price_kopecks"] - r["paid_kopecks"]) for r in rows]


def prescription_print_data(conn, visit_id: int) -> tuple[dict, list[dict]]:
    head = conn.execute(
        """SELECT a.appt_date, an.name AS animal, an.species, o.full_name AS owner, v.full_name AS vet, vi.diagnosis
           FROM visits vi JOIN appointments a ON a.id = vi.appointment_id
           JOIN animals an ON an.id = a.animal_id JOIN owners o ON o.id = an.owner_id JOIN vets v ON v.id = a.vet_id
           WHERE vi.id = ?""", (visit_id,)).fetchone()
    items = conn.execute(
        """SELECT m.name AS medication, p.dosage, p.course_days, p.qty, m.unit
           FROM prescriptions p JOIN medications m ON m.id = p.medication_id WHERE p.visit_id = ? ORDER BY p.id""",
        (visit_id,)).fetchall()
    h = dict(head)
    from app.util import fmt_date
    h["date"] = fmt_date(h.pop("appt_date"))
    return h, [dict(i) for i in items]


def invoice_print_data(conn, appointment_id: int) -> dict:
    """Счёт выставляется по записи — его можно распечатать сразу при записи (для предоплаты)."""
    r = conn.execute(
        """SELECT a.id AS number, a.appt_date AS date, a.appt_time AS time, an.name AS animal,
                  o.full_name AS owner, v.full_name AS vet, s.name AS service, a.price_kopecks AS price,
                  COALESCE((SELECT SUM(CASE p.status WHEN 'оплачен' THEN p.amount_kopecks
                                                     WHEN 'возврат' THEN -p.amount_kopecks ELSE 0 END)
                            FROM payments p WHERE p.appointment_id = a.id), 0) AS paid
           FROM appointments a
           JOIN animals an ON an.id = a.animal_id JOIN owners o ON o.id = an.owner_id
           JOIN vets v ON v.id = a.vet_id JOIN services s ON s.id = a.service_id WHERE a.id = ?""",
        (appointment_id,)).fetchone()
    return dict(r)
