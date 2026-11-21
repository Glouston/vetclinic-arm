"""Владельцы и животные: списки, CRUD, данные карточки животного. Только параметризованный SQL."""
from __future__ import annotations
import sqlite3

from app.errors import UserError
from app.models import Animal, Owner, Payment, PrescriptionRow, Vaccination
from app.util import normalize_phone, today_iso


def _like(text: str | None) -> str | None:
    """Строка поиска -> шаблон LIKE (спецсимволы экранируются, пустая строка = без фильтра).

    Шаблон приводится к нижнему регистру; в SQL сравнивается с ulower(поле), т.к. встроенные
    LIKE/lower() SQLite не меняют регистр кириллицы («барсик» не находил «Барсик»).
    """
    text = (text or "").strip().lower()
    if not text:
        return None
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


# ------------------------------------------------------------------ владельцы
def list_owners(conn: sqlite3.Connection, search: str | None = None) -> list[Owner]:
    rows = conn.execute(
        """SELECT o.id, o.full_name, o.phone, o.address, o.email,
                  (SELECT COUNT(*) FROM animals a WHERE a.owner_id = o.id) AS animals_count
           FROM owners o
           WHERE :s IS NULL OR ulower(o.full_name) LIKE :s ESCAPE '\\' OR ulower(o.phone) LIKE :s ESCAPE '\\'
           ORDER BY o.full_name""",
        {"s": _like(search)},
    ).fetchall()
    return [Owner.from_row(r) for r in rows]


def get_owner(conn: sqlite3.Connection, owner_id: int) -> Owner | None:
    r = conn.execute(
        """SELECT o.id, o.full_name, o.phone, o.address, o.email,
                  (SELECT COUNT(*) FROM animals a WHERE a.owner_id = o.id) AS animals_count
           FROM owners o WHERE o.id = ?""", (owner_id,)).fetchone()
    return Owner.from_row(r) if r else None


def create_owner(conn, full_name: str, phone: str, address: str | None = None, email: str | None = None) -> int:
    if not full_name.strip():
        raise UserError("Укажите ФИО владельца.")
    cur = conn.execute(
        "INSERT INTO owners (full_name, phone, address, email) VALUES (?, ?, ?, ?)",
        (full_name.strip(), normalize_phone(phone), (address or "").strip() or None, (email or "").strip() or None))
    return cur.lastrowid


def update_owner(conn, owner_id: int, full_name: str, phone: str, address: str | None, email: str | None) -> None:
    if not full_name.strip():
        raise UserError("Укажите ФИО владельца.")
    conn.execute(
        "UPDATE owners SET full_name = ?, phone = ?, address = ?, email = ? WHERE id = ?",
        (full_name.strip(), normalize_phone(phone), (address or "").strip() or None,
         (email or "").strip() or None, owner_id))


def delete_owner(conn, owner_id: int) -> None:
    n = conn.execute("SELECT COUNT(*) FROM animals WHERE owner_id = ?", (owner_id,)).fetchone()[0]
    if n:
        raise UserError(f"Нельзя удалить владельца: есть связанные записи (животных: {n}).")
    conn.execute("DELETE FROM owners WHERE id = ?", (owner_id,))


def search_phones(conn, prefix: str, limit: int = 15) -> list[tuple[int, str, str]]:
    """Для автодополнения: (id, телефон, ФИО) по фрагменту телефона или ФИО."""
    rows = conn.execute(
        """SELECT id, phone, full_name FROM owners
           WHERE ulower(phone) LIKE :s ESCAPE '\\' OR ulower(full_name) LIKE :s ESCAPE '\\'
           ORDER BY phone LIMIT :n""", {"s": _like(prefix) or "%", "n": limit}).fetchall()
    return [(r["id"], r["phone"], r["full_name"]) for r in rows]


def find_owner_by_phone(conn, phone: str) -> Owner | None:
    try:
        norm = normalize_phone(phone)
    except UserError:
        return None
    r = conn.execute("SELECT id FROM owners WHERE phone = ?", (norm,)).fetchone()
    return get_owner(conn, r["id"]) if r else None


# ------------------------------------------------------------------- животные
_ANIMAL_SELECT = """
SELECT an.id, an.owner_id, an.name, an.species, an.breed, an.birth_date, an.sex, an.notes,
       o.full_name AS owner_name, o.phone AS owner_phone,
       r.next_due_date,
       CASE WHEN r.next_due_date IS NULL THEN 'нет данных'
            WHEN r.next_due_date < :today THEN 'просрочена'
            WHEN r.next_due_date <= date(:today, '+30 days') THEN 'скоро'
            ELSE 'в норме' END AS vacc_status
FROM animals an
JOIN owners o ON o.id = an.owner_id
LEFT JOIN v_animal_revaccination r ON r.animal_id = an.id
"""


def list_animals(conn, search: str | None = None, species: str | None = None, sex: str | None = None,
                 only_overdue: bool = False, today: str | None = None) -> list[Animal]:
    """Фильтры применяются совместно (AND), всё считается в SQL."""
    rows = conn.execute(
        _ANIMAL_SELECT + """
        WHERE (:s IS NULL OR ulower(an.name) LIKE :s ESCAPE '\\' OR ulower(o.full_name) LIKE :s ESCAPE '\\' OR ulower(o.phone) LIKE :s ESCAPE '\\')
          AND (:species IS NULL OR an.species = :species)
          AND (:sex IS NULL OR an.sex = :sex)
          AND (:overdue = 0 OR r.next_due_date < :today)
        ORDER BY an.name""",
        {"s": _like(search), "species": species or None, "sex": sex or None,
         "overdue": 1 if only_overdue else 0, "today": today or today_iso()}).fetchall()
    return [Animal.from_row(r) for r in rows]


def get_animal(conn, animal_id: int, today: str | None = None) -> Animal | None:
    r = conn.execute(_ANIMAL_SELECT + " WHERE an.id = :id", {"id": animal_id, "today": today or today_iso()}).fetchone()
    return Animal.from_row(r) if r else None


def list_species(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT species FROM animals ORDER BY species")]


def animals_of_owner(conn, owner_id: int) -> list[tuple[int, str, str]]:
    rows = conn.execute("SELECT id, name, species FROM animals WHERE owner_id = ? ORDER BY name", (owner_id,))
    return [(r["id"], r["name"], r["species"]) for r in rows]


def create_animal(conn, owner_id: int, name: str, species: str, breed: str | None = None,
                  birth_date: str | None = None, sex: str | None = None, notes: str | None = None) -> int:
    if not name.strip() or not species.strip():
        raise UserError("Укажите кличку и вид животного.")
    cur = conn.execute(
        "INSERT INTO animals (owner_id, name, species, breed, birth_date, sex, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (owner_id, name.strip(), species.strip(), breed or None, birth_date or None, sex or None, notes or None))
    return cur.lastrowid


def update_animal(conn, animal_id: int, owner_id: int, name: str, species: str, breed: str | None,
                  birth_date: str | None, sex: str | None) -> None:
    if not name.strip() or not species.strip():
        raise UserError("Укажите кличку и вид животного.")
    conn.execute(
        "UPDATE animals SET owner_id = ?, name = ?, species = ?, breed = ?, birth_date = ?, sex = ? WHERE id = ?",
        (owner_id, name.strip(), species.strip(), breed or None, birth_date or None, sex or None, animal_id))


def update_animal_notes(conn, animal_id: int, notes: str) -> None:
    conn.execute("UPDATE animals SET notes = ? WHERE id = ?", (notes.strip() or None, animal_id))


def delete_animal(conn, animal_id: int) -> None:
    n = conn.execute("SELECT COUNT(*) FROM appointments WHERE animal_id = ?", (animal_id,)).fetchone()[0]
    if n:
        raise UserError(f"Нельзя удалить животное: есть история приёмов (записей: {n}).")
    conn.execute("DELETE FROM animals WHERE id = ?", (animal_id,))  # вакцинации/напоминания — каскадом


# ----------------------------------------------------------- вкладки карточки
def vaccinations_of(conn, animal_id: int) -> list[Vaccination]:
    rows = conn.execute(
        """SELECT v.id, m.name AS medication_name, v.vacc_date, v.next_due_date
           FROM vaccinations v JOIN medications m ON m.id = v.medication_id
           WHERE v.animal_id = ? ORDER BY v.vacc_date DESC""", (animal_id,)).fetchall()
    return [Vaccination.from_row(r) for r in rows]


def add_vaccination(conn, animal_id: int, medication_id: int, vacc_date: str, next_due_date: str | None) -> int:
    if next_due_date and next_due_date <= vacc_date:
        raise UserError("Дата ревакцинации должна быть позже даты вакцинации.")
    cur = conn.execute(
        "INSERT INTO vaccinations (animal_id, medication_id, vacc_date, next_due_date) VALUES (?, ?, ?, ?)",
        (animal_id, medication_id, vacc_date, next_due_date or None))
    return cur.lastrowid


def prescriptions_of(conn, animal_id: int) -> list[PrescriptionRow]:
    rows = conn.execute(
        """SELECT p.id, a.appt_date, m.name AS medication_name, p.dosage, p.course_days, p.qty, m.unit,
                  v.full_name AS vet_name
           FROM prescriptions p
           JOIN visits vi ON vi.id = p.visit_id
           JOIN appointments a ON a.id = vi.appointment_id
           JOIN medications m ON m.id = p.medication_id
           JOIN vets v ON v.id = a.vet_id
           WHERE a.animal_id = ? ORDER BY a.appt_date DESC, p.id""", (animal_id,)).fetchall()
    return [PrescriptionRow.from_row(r) for r in rows]


def payments_of(conn, animal_id: int) -> list[Payment]:
    rows = conn.execute(
        """SELECT p.id, p.appointment_id, a.appt_date, s.name AS service_name,
                  p.amount_kopecks, p.method, p.status, p.paid_at
           FROM payments p
           JOIN appointments a ON a.id = p.appointment_id
           JOIN services s ON s.id = a.service_id
           WHERE a.animal_id = ? ORDER BY a.appt_date DESC, p.id""", (animal_id,)).fetchall()
    return [Payment.from_row(r) for r in rows]


def animal_debt_kopecks(conn, animal_id: int) -> int:
    return conn.execute("SELECT COALESCE(SUM(debt_kopecks), 0) FROM v_debt_visits WHERE animal_id = ?",
                        (animal_id,)).fetchone()[0]


def weight_points(conn, animal_id: int) -> list[tuple[str, float]]:
    """Динамика веса: (дата приёма, кг) по vital_signs."""
    rows = conn.execute(
        """SELECT a.appt_date, vs.weight_kg
           FROM vital_signs vs
           JOIN visits vi ON vi.id = vs.visit_id
           JOIN appointments a ON a.id = vi.appointment_id
           WHERE a.animal_id = ? AND vs.weight_kg IS NOT NULL
           ORDER BY a.appt_date, vs.id""", (animal_id,)).fetchall()
    return [(r["appt_date"], float(r["weight_kg"])) for r in rows]
