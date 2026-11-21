"""Генератор seed.sql — вымышленные, логически согласованные тестовые данные.

Запуск:  python tools/gen_seed.py [--today ГГГГ-ММ-ДД] > seed.sql
Данные детерминированы (random.Random(42)); даты считаются от --today
(по умолчанию 2026-10-28, на эту дату и сформирован поставляемый seed.sql).
Склад моделируется: остатки партий = приход − списания по приёмам (FIFO).
"""
from __future__ import annotations
import argparse
import random
from datetime import date, datetime, timedelta

ap = argparse.ArgumentParser()
ap.add_argument("--today", default="2026-10-28")
TODAY = date.fromisoformat(ap.parse_args().today)
rnd = random.Random(42)


def d(offset: int) -> date:
    return TODAY + timedelta(days=offset)


def q(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


out: list[str] = []


def insert(table: str, cols: list[str], rows: list[tuple]) -> None:
    if not rows:
        return
    out.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES")
    out.append(",\n".join("  (" + ", ".join(q(x) for x in r) + ")" for r in rows) + ";\n")


# ---------------------------------------------------------------- справочники
vets = [
    (1, "Соколова Анна Викторовна", "Терапевт", "+375291110001", 1),
    (2, "Петров Игорь Сергеевич", "Терапевт", "+375291110002", 1),
    (3, "Крылов Дмитрий Андреевич", "Хирург", "+375291110003", 1),
    (4, "Белова Марина Олеговна", "Дерматолог", "+375291110004", 1),
    (5, "Орлов Павел Николаевич", "Кардиолог", "+375291110005", 1),
    (6, "Зайцева Елена Игоревна", "Стоматолог", "+375291110006", 1),
    (7, "Громов Виктор Павлович", "Терапевт", "+375291110007", 0),  # уволен: не участвует в записях
]
# id, name, category, duration, required_specialization, [(price_byn, from, to)]
services = [
    (1, "Первичный приём", "Приём", 30, "Терапевт", [(35, "2025-01-01", "2026-05-31"), (42, "2026-06-01", None)]),
    (2, "Повторный приём", "Приём", 20, "Терапевт", [(25, "2025-01-01", None)]),
    (3, "Вакцинация", "Профилактика", 20, "Терапевт", [(32, "2025-01-01", "2026-09-30"), (37, "2026-10-01", None)]),
    (4, "УЗИ брюшной полости", "Диагностика", 40, None, [(75, "2025-01-01", None)]),
    (5, "Общий анализ крови", "Диагностика", 15, None, [(30, "2025-01-01", None)]),
    (6, "ЭКГ", "Диагностика", 30, "Кардиолог", [(60, "2025-01-01", None)]),
    (7, "Консультация кардиолога", "Приём", 30, "Кардиолог", [(50, "2025-01-01", None)]),
    (8, "Кастрация / стерилизация", "Хирургия", 90, "Хирург", [(180, "2025-01-01", "2026-06-30"), (200, "2026-07-01", None)]),
    (9, "Удаление новообразования", "Хирургия", 120, "Хирург", [(300, "2025-01-01", None)]),
    (10, "Кожный скрейпинг", "Дерматология", 25, "Дерматолог", [(38, "2025-01-01", None)]),
    (11, "Консультация дерматолога", "Дерматология", 30, "Дерматолог", [(45, "2025-01-01", None)]),
    (12, "Ультразвуковая чистка зубов", "Стоматология", 60, "Стоматолог", [(120, "2025-01-01", None)]),
]
meds = [  # id, name, unit, is_vaccine
    (1, "Нобивак DHPPi", "доза", 1),
    (2, "Нобивак Rabies", "доза", 1),
    (3, "Нобивак Tricat Trio", "доза", 1),
    (4, "Амоксициллин 15%", "мл", 0),
    (5, "Мелоксикам 0,5 мг/мл", "мл", 0),
    (6, "Преднизолон 30 мг/мл", "мл", 0),
    (7, "Цефтриаксон 1 г", "флакон", 0),
    (8, "Фуросемид 1%", "мл", 0),
    (9, "Рингера раствор", "флакон", 0),
    (10, "Дроталевет", "таблетка", 0),
    (11, "Энтеросгель", "упаковка", 0),
    (12, "Ронколейкин", "доза", 0),
]
vaccine_ids = [1, 2, 3]
drug_ids = [m[0] for m in meds if not m[3]]

first_f = ["Анна", "Мария", "Елена", "Ольга", "Татьяна", "Наталья", "Ирина", "Светлана", "Юлия", "Екатерина"]
first_m = ["Алексей", "Дмитрий", "Сергей", "Иван", "Андрей", "Михаил", "Николай", "Павел", "Артём", "Роман"]
last = ["Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев", "Морозов", "Волков", "Фёдоров", "Михайлов", "Новиков",
        "Макаров", "Никитин", "Захаров", "Зайцев", "Соловьёв", "Борисов", "Яковлев", "Григорьев", "Романов", "Сорокин"]
streets = ["ул. Ленина", "ул. Мира", "пр. Победы", "ул. Садовая", "ул. Гагарина", "ул. Лесная"]
owners = []
for i in range(1, 21):
    male = i % 2 == 1
    ln = last[i - 1] + ("" if male else "а")
    fn = rnd.choice(first_m if male else first_f)
    pn = rnd.choice(["Александр", "Сергей", "Игорь", "Олег"]) + ("ович" if male else "овна")
    owners.append((i, f"{ln} {fn} {pn}", f"+37529{2000000 + i * 37:07d}",
                   f"{rnd.choice(streets)}, д. {rnd.randint(1, 80)}, кв. {rnd.randint(1, 120)}",
                   f"user{i}@example.com" if i % 3 else None))
# владельцы 19, 20 — без животных (демо NOT EXISTS)

animal_defs = [  # name, species, breed, sex, base_weight
    ("Барсик", "Кот", "Британская", "M", 5.2), ("Муся", "Кошка", "Сибирская", "F", 4.1),
    ("Рекс", "Собака", "Овчарка", "M", 32.0), ("Лайка", "Собака", "Хаски", "F", 22.0),
    ("Персик", "Кот", "Персидская", "M", 4.8), ("Белка", "Собака", "Шпиц", "F", 3.2),
    ("Мурка", "Кошка", "Беспородная", "F", 3.9), ("Бобик", "Собака", "Дворняга", "M", 14.0),
    ("Симба", "Кот", "Мейн-кун", "M", 7.5), ("Дейзи", "Собака", "Лабрадор", "F", 26.0),
    ("Тоша", "Кот", "Шотландская", "M", 5.0), ("Грета", "Собака", "Такса", "F", 8.4),
    ("Чара", "Кошка", "Бенгальская", "F", 3.6), ("Макс", "Собака", "Корги", "M", 11.5),
    ("Фиона", "Кошка", "Беспородная", "F", 3.3), ("Арчи", "Собака", "Бигль", "M", 12.2),
    ("Луна", "Кошка", "Русская голубая", "F", 3.8), ("Граф", "Собака", "Ротвейлер", "M", 41.0),
    ("Кеша", "Попугай", "Волнистый", "M", 0.04), ("Зевс", "Собака", "Доберман", "M", 35.0),
    ("Ириска", "Кошка", "Беспородная", "F", 3.5), ("Пушок", "Кролик", "Декоративный", "M", 1.9),
    ("Буся", "Собака", "Мопс", "F", 8.0), ("Снежок", "Кот", "Беспородный", "M", 4.4),
    ("Шерри", "Собака", "Пудель", "F", 6.5), ("Борис", "Кот", "Британская", "M", 6.1),
    ("Тиша", "Хомяк", "Джунгарский", "M", 0.05), ("Найда", "Собака", "Колли", "F", 24.0),
    ("Оскар", "Кот", "Девон-рекс", "M", 3.9), ("Жучка", "Собака", "Дворняга", "F", 13.0),
]
animals = []
for i, (nm, sp, br, sx, w) in enumerate(animal_defs, 1):
    owner_id = (i - 1) % 18 + 1  # владельцы 1..18, 19-20 без животных
    bd = d(-rnd.randint(200, 3600)).isoformat()
    animals.append((i, owner_id, nm, sp, br, bd, sx, "Аллергия на курицу" if i % 11 == 0 else None))
base_weight = {i: a[4] for i, a in enumerate(animal_defs, 1)}
NO_VISIT_ANIMALS = {29, 30}  # животные без приёмов (демо NOT EXISTS / удаление разрешено)

# --------------------------------------------------------------------- склад
batch_defs = [  # med, batch_no, initial qty, expiry, received
    (4, "AMX-2401", 60, d(300), d(-120)), (4, "AMX-2503", 80, d(500), d(-30)),
    (5, "MLX-2402", 50, d(18), d(-150)), (5, "MLX-2511", 70, d(420), d(-20)),
    (6, "PRD-2310", 25, d(-40), d(-300)), (6, "PRD-2505", 60, d(260), d(-60)),
    (7, "CFT-2406", 40, d(25), d(-140)), (7, "CFT-2509", 60, d(380), d(-40)),
    (8, "FRS-2503", 8, d(12), d(-90)),
    (9, "RNG-2412", 30, d(220), d(-110)), (10, "DRT-2501", 120, d(330), d(-100)),
    (11, "ENT-2502", 40, d(450), d(-80)), (12, "RNK-2504", 30, d(150), d(-70)),
    (1, "NDP-2501", 40, d(200), d(-120)), (2, "NRB-2502", 40, d(210), d(-120)), (3, "NTR-2503", 30, d(190), d(-120)),
]
batches = {}  # id -> dict
movements = []  # (batch_id, visit_id, delta, reason, moved_at)
for bid, (mid, no, qty, exp, rec) in enumerate(batch_defs, 1):
    batches[bid] = dict(med=mid, no=no, qty=qty, exp=exp)
    movements.append((bid, None, qty, "Приход по накладной", f"{rec.isoformat()} 10:00:00"))

# ------------------------------------------------------------------- записи
spec_vets = {}
for v in vets:
    if v[4]:
        spec_vets.setdefault(v[2], []).append(v[0])
all_active = [v[0] for v in vets if v[4]]
svc_by_id = {s[0]: s for s in services}


def price_on(sid: int, on: date) -> int:
    for byn, vf, vt in svc_by_id[sid][5]:
        if date.fromisoformat(vf) <= on and (vt is None or on <= date.fromisoformat(vt)):
            return byn * 100
    return svc_by_id[sid][5][0][0] * 100


slots = [f"{h:02d}:{m:02d}" for h in range(9, 18) for m in (0, 30)]
used = set()
raw = []  # (date, time, animal, vet, service)
offsets = [rnd.randint(-80, 21) for _ in range(52)] + [0] * 6 + [1] * 3 + [2, 3]
vaccine_service_first = {}
for off in offsets:
    day = d(off)
    animal = rnd.choice([a for a in range(1, 31) if a not in NO_VISIT_ANIMALS])
    sid = rnd.choices([s[0] for s in services], weights=[14, 8, 14, 6, 8, 4, 4, 4, 2, 6, 4, 2])[0]
    spec = svc_by_id[sid][4]
    pool = spec_vets[spec] if spec else all_active
    for _ in range(40):
        vet = rnd.choice(pool)
        t = rnd.choice(slots)
        if (vet, day, t) not in used:
            used.add((vet, day, t))
            raw.append((day, t, animal, vet, sid))
            break
raw.sort()

appts, visits, prescs, payments, vaccs, vitals, reminders = [], [], [], [], [], [], []
vid = 0
pid = 0
for aid, (day, t, animal, vet, sid) in enumerate(raw, 1):
    created = day - timedelta(days=rnd.randint(1, 5))
    price = price_on(sid, created)
    if day < TODAY:
        status = rnd.choices(["завершён", "отменён", "подтверждён"], weights=[78, 15, 7])[0]
    elif day == TODAY:
        status = rnd.choice(["запланирован", "подтверждён", "подтверждён"])
    else:
        status = rnd.choices(["запланирован", "подтверждён", "отменён"], weights=[50, 42, 8])[0]
    appts.append((aid, animal, vet, sid, day.isoformat(), t, status, price, f"{created.isoformat()} 12:00:00"))
    if status != "завершён":
        continue
    vid += 1
    closed = f"{day.isoformat()} {t}:00"
    cat = svc_by_id[sid][2]
    diag = None if cat == "Профилактика" else rnd.choice(
        ["Гастроэнтерит", "Дерматит", "Отит", "Здоров", "Аллергическая реакция", "Хронический гастрит", "Ушиб", "Конъюнктивит"])
    visits.append((vid, aid, diag, rnd.choice(["Вялость, отказ от корма", "Зуд, расчёсы", "Плановый осмотр", "Рвота", "Хромота"]), closed))
    # назначения + списание FIFO
    if cat in ("Приём", "Диагностика", "Хирургия", "Дерматология") and rnd.random() < 0.65:
        for mid in rnd.sample(drug_ids, rnd.choice([1, 1, 2])):
            need = rnd.randint(1, 4)
            cands = sorted((b for b, x in batches.items() if x["med"] == mid and x["qty"] > 0 and x["exp"] >= day),
                           key=lambda b: batches[b]["exp"])
            if sum(batches[b]["qty"] for b in cands) < need:
                continue
            prescs.append((len(prescs) + 1, vid, mid, rnd.choice(["1 раз в день", "2 раза в день", "по 1 ед. утром"]),
                           rnd.choice([3, 5, 7, 10]), need))
            left = need
            for b in cands:
                take = min(left, batches[b]["qty"])
                batches[b]["qty"] -= take
                movements.append((b, vid, -take, "Списание по назначению", closed))
                left -= take
                if left == 0:
                    break
    # вакцинация как результат услуги
    if sid == 3:
        mid = rnd.choice(vaccine_ids)
        vaccs.append((animal, mid, day.isoformat(), (day + timedelta(days=365)).isoformat()))
    # показатели
    w = round(base_weight[animal] * (1 + (day - TODAY).days / 2000 + rnd.uniform(-0.03, 0.03)), 2)
    temp = None if rnd.random() < 0.2 else round(rnd.uniform(37.8, 39.4), 1)
    vitals.append((vid, w, temp, closed))
    # оплата
    age = (TODAY - day).days
    mode = rnd.choices(["paid", "partial", "pending"], weights=[70, 8, 22])[0]
    if age < 3:
        mode = rnd.choice(["pending", "paid"])
    methods = ["наличные", "карта", "перевод"]
    if mode == "paid":
        pid += 1
        payments.append((pid, aid, price, rnd.choice(methods), "оплачен", closed))
    elif mode == "partial" and price >= 200:
        half = price // 2
        pid += 1
        payments.append((pid, aid, half, rnd.choice(methods), "оплачен", closed))
        pid += 1
        payments.append((pid, aid, price - half, None, "ожидает", None))
    else:
        pid += 1
        payments.append((pid, aid, price, None, "ожидает", None))
        if age > 14:
            reminders.append((animal, "оплата", (day + timedelta(days=14)).isoformat(), "просрочено"))

# предоплата при записи (отдельный генератор, чтобы не менять остальные данные):
# часть будущих записей оплачена заранее полностью/частично; по отменённой — возврат
rnd_pre = random.Random(7)
cancel_after = []  # оплачено заранее, затем отменено: в seed статус меняется после вставки платежей
for idx, (aid, _animal, _vet, _sid, day_s, t, status, price, created_at) in enumerate(appts):
    if day_s < TODAY.isoformat() or status == "завершён":
        continue
    roll = rnd_pre.random()
    paid_at = created_at
    if status == "отменён":
        if roll < 0.6:
            appts[idx] = appts[idx][:6] + ("запланирован",) + appts[idx][7:]
            cancel_after.append(aid)
            pid += 1
            payments.append((pid, aid, price, "карта", "оплачен", paid_at))
            pid += 1
            payments.append((pid, aid, price, "карта", "возврат", paid_at[:10] + " 18:00:00"))
    elif roll < 0.30:
        pid += 1
        payments.append((pid, aid, price, rnd_pre.choice(["карта", "перевод"]), "оплачен", paid_at))
    elif roll < 0.45 and price >= 200:
        pid += 1
        payments.append((pid, aid, price // 2, rnd_pre.choice(["наличные", "карта"]), "оплачен", paid_at))

# исторические вакцинации (ревакцинация): просроченные, скоро, в норме
hist = [(1, 1, -430), (2, 3, -400), (3, 1, -380), (3, 2, -380), (4, 1, -350), (5, 3, -420), (6, 1, -345),
        (7, 3, -250), (8, 2, -360), (9, 1, -340), (10, 1, -100), (10, 2, -100), (11, 3, -200), (12, 1, -362),
        (13, 3, -120), (14, 2, -380), (15, 3, -90), (16, 1, -335), (17, 3, -30), (18, 1, -500), (20, 1, -150)]
for animal, mid, off in hist:
    vd = d(off)
    if any(v[0] == animal and v[1] == mid and v[2] == vd.isoformat() for v in vaccs):
        continue
    vaccs.append((animal, mid, vd.isoformat(), (vd + timedelta(days=365)).isoformat()))
vaccs = [(i,) + v for i, v in enumerate(sorted(set(vaccs), key=lambda x: (x[0], x[2], x[1])), 1)]

# напоминания по ревакцинации (последняя вакцинация по препарату)
latest = {}
for _, an, mid, vd, due in vaccs:
    if (an, mid) not in latest or vd > latest[(an, mid)][0]:
        latest[(an, mid)] = (vd, due)
for (an, mid), (vd, due) in latest.items():
    dd = date.fromisoformat(due)
    if dd < TODAY:
        reminders.append((an, "ревакцинация", due, "просрочено" if an % 4 else "выполнено"))
    elif dd <= TODAY + timedelta(days=30):
        reminders.append((an, "ревакцинация", due, "запланировано"))
reminders = [(i,) + r for i, r in enumerate(sorted(set(reminders)), 1)]

# ---------------------------------------------------------------- вывод SQL
out.append("-- Тестовые данные (сгенерировано tools/gen_seed.py, дата отсчёта %s)." % TODAY.isoformat())
out.append("-- Вымышленные данные. Применять к БД, созданной schema.sql.")
out.append("PRAGMA foreign_keys = ON;\nBEGIN;\n")
insert("owners", ["id", "full_name", "phone", "address", "email"], owners)
insert("vets", ["id", "full_name", "specialization", "phone", "is_active"], vets)
insert("services", ["id", "name", "category", "duration_min", "required_specialization"],
       [(s[0], s[1], s[2], s[3], s[4]) for s in services])
prices = []
for s in services:
    for byn, vf, vt in s[5]:
        prices.append((len(prices) + 1, s[0], byn * 100, vf, vt))
insert("service_prices", ["id", "service_id", "price_kopecks", "valid_from", "valid_to"], prices)
insert("medications", ["id", "name", "unit"], [(m[0], m[1], m[2]) for m in meds])
insert("animals", ["id", "owner_id", "name", "species", "breed", "birth_date", "sex", "notes"], animals)
insert("appointments", ["id", "animal_id", "vet_id", "service_id", "appt_date", "appt_time", "status", "price_kopecks", "created_at"], appts)
insert("visits", ["id", "appointment_id", "diagnosis", "complaints", "closed_at"], visits)
insert("prescriptions", ["id", "visit_id", "medication_id", "dosage", "course_days", "qty"], prescs)
insert("stock_batches", ["id", "medication_id", "batch_no", "qty", "expiry_date"],
       [(b, x["med"], x["no"], x["qty"], x["exp"].isoformat()) for b, x in batches.items()])
insert("stock_movements", ["id", "batch_id", "visit_id", "qty_delta", "reason", "moved_at"],
       [(i,) + m for i, m in enumerate(movements, 1)])
insert("payments", ["id", "appointment_id", "amount_kopecks", "method", "status", "paid_at"], payments)
if cancel_after:
    out.append("-- записи, оплаченные заранее и затем отменённые (переход запланирован → отменён, возврат выше)")
    out.append("UPDATE appointments SET status = 'отменён' WHERE id IN (%s);\n" % ", ".join(map(str, cancel_after)))
insert("vaccinations", ["id", "animal_id", "medication_id", "vacc_date", "next_due_date"], vaccs)
insert("vital_signs", ["id", "visit_id", "weight_kg", "temp_c", "measured_at"],
       [(i,) + v for i, v in enumerate(vitals, 1)])
insert("reminders", ["id", "animal_id", "kind", "due_date", "status"], reminders)
out.append("COMMIT;")
print("\n".join(out))
