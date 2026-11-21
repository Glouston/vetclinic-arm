"""Dataclass-модели строк, которые репозитории отдают UI (SQL остаётся в репозиториях)."""
from __future__ import annotations
from dataclasses import dataclass, fields
from sqlite3 import Row
from typing import Type, TypeVar

T = TypeVar("T", bound="_FromRow")


class _FromRow:
    @classmethod
    def from_row(cls: Type[T], row: Row) -> T:
        return cls(**{f.name: row[f.name] for f in fields(cls)})  # type: ignore[arg-type]


@dataclass
class Owner(_FromRow):
    id: int
    full_name: str
    phone: str
    address: str | None
    email: str | None
    animals_count: int = 0


@dataclass
class Animal(_FromRow):
    id: int
    owner_id: int
    name: str
    species: str
    breed: str | None
    birth_date: str | None
    sex: str | None
    notes: str | None
    owner_name: str
    owner_phone: str
    next_due_date: str | None
    vacc_status: str  # просрочена | скоро | в норме | нет данных


@dataclass
class Vet(_FromRow):
    id: int
    full_name: str
    specialization: str
    phone: str | None
    is_active: int


@dataclass
class Service(_FromRow):
    id: int
    name: str
    category: str | None
    duration_min: int | None
    required_specialization: str | None
    price_kopecks: int | None  # действующая сейчас цена


@dataclass
class PriceVersion(_FromRow):
    id: int
    service_id: int
    price_kopecks: int
    valid_from: str
    valid_to: str | None


@dataclass
class Medication(_FromRow):
    id: int
    name: str
    unit: str


@dataclass
class Appointment(_FromRow):
    id: int
    appt_date: str
    appt_time: str
    status: str
    price_kopecks: int
    animal_id: int
    animal_name: str
    owner_name: str
    owner_phone: str
    vet_id: int
    vet_name: str
    service_id: int
    service_name: str
    visit_id: int | None
    paid_kopecks: int


@dataclass
class Batch(_FromRow):
    id: int
    medication_id: int
    medication_name: str
    unit: str
    batch_no: str
    qty: int
    expiry_date: str
    state: str  # в норме | истекает | просрочен


@dataclass
class Vaccination(_FromRow):
    id: int
    medication_name: str
    vacc_date: str
    next_due_date: str | None


@dataclass
class PrescriptionRow(_FromRow):
    id: int
    appt_date: str
    medication_name: str
    dosage: str
    course_days: int | None
    qty: int
    unit: str
    vet_name: str


@dataclass
class Payment(_FromRow):
    id: int
    appointment_id: int
    appt_date: str
    service_name: str
    amount_kopecks: int
    method: str | None
    status: str
    paid_at: str | None


@dataclass
class Reminder(_FromRow):
    id: int
    animal_id: int
    animal_name: str
    owner_name: str
    kind: str
    due_date: str
    status: str


@dataclass
class Movement(_FromRow):
    id: int
    moved_at: str
    medication_name: str
    batch_no: str
    qty_delta: int
    reason: str


@dataclass
class DashboardStats:
    today_appointments: int
    unpaid_visits: int
    overdue_vaccinations: int
    expiring_batches: int


@dataclass
class PrescriptionInput:
    medication_id: int
    dosage: str
    course_days: int | None
    qty: int


@dataclass
class VisitRow(_FromRow):
    visit_id: int
    appointment_id: int
    appt_date: str
    animal_name: str
    owner_name: str
    vet_name: str
    service_name: str
    diagnosis: str | None
    price_kopecks: int
    paid_kopecks: int
    debt_kopecks: int
