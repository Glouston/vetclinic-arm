-- ============================================================================
-- АРМ диспетчера ветеринарной клиники — схема БД (SQLite 3)
-- Деньги: INTEGER, копейки (*_kopecks). Даты: TEXT 'YYYY-MM-DD'. Время: 'HH:MM'.
-- В каждом соединении обязательно: PRAGMA foreign_keys = ON;
-- Скрипт идемпотентен только на пустой БД: повторный запуск ничего не очищает
-- (CREATE ... IF NOT EXISTS), приложение схему не пересоздаёт.
-- ============================================================================
PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- Справочники и участники
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS owners (
    id        INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL CHECK (length(trim(full_name)) > 0),
    phone     TEXT NOT NULL UNIQUE CHECK (phone GLOB '+375[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
    address   TEXT,
    email     TEXT CHECK (email IS NULL OR email LIKE '%_@_%._%')
);

CREATE TABLE IF NOT EXISTS animals (
    id         INTEGER PRIMARY KEY,
    owner_id   INTEGER NOT NULL REFERENCES owners(id) ON DELETE RESTRICT,
    name       TEXT NOT NULL CHECK (length(trim(name)) > 0),
    species    TEXT NOT NULL CHECK (length(trim(species)) > 0),
    breed      TEXT,
    birth_date TEXT CHECK (birth_date IS NULL OR (date(birth_date) IS NOT NULL AND date(birth_date) = birth_date)),
    sex        TEXT CHECK (sex IN ('M', 'F')),
    notes      TEXT
);
CREATE INDEX IF NOT EXISTS ix_animals_owner ON animals(owner_id);

CREATE TABLE IF NOT EXISTS vets (
    id             INTEGER PRIMARY KEY,
    full_name      TEXT NOT NULL CHECK (length(trim(full_name)) > 0),
    specialization TEXT NOT NULL CHECK (length(trim(specialization)) > 0),
    phone          TEXT,
    is_active      INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- required_specialization: какой специализации врач может оказывать услугу
-- (NULL — любой врач). Нужно для правила «нельзя записать к врачу не той
-- специализации» (ТЗ п.3) и для фильтра врачей в диалоге записи.
CREATE TABLE IF NOT EXISTS services (
    id                      INTEGER PRIMARY KEY,
    name                    TEXT NOT NULL UNIQUE CHECK (length(trim(name)) > 0),
    category                TEXT,
    duration_min            INTEGER CHECK (duration_min IS NULL OR duration_min > 0),
    required_specialization TEXT
);

-- История цен (ТЗ п.5.4): новая цена = новая строка, старая закрывается valid_to.
CREATE TABLE IF NOT EXISTS service_prices (
    id           INTEGER PRIMARY KEY,
    service_id   INTEGER NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
    price_kopecks INTEGER NOT NULL CHECK (price_kopecks >= 0),
    valid_from   TEXT NOT NULL CHECK (date(valid_from) IS NOT NULL AND date(valid_from) = valid_from),
    valid_to     TEXT CHECK (valid_to IS NULL OR (date(valid_to) IS NOT NULL AND date(valid_to) = valid_to)),
    UNIQUE (service_id, valid_from),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
-- не более одной «открытой» (текущей) цены на услугу
CREATE UNIQUE INDEX IF NOT EXISTS ux_service_prices_open
    ON service_prices(service_id) WHERE valid_to IS NULL;

-- ----------------------------------------------------------------------------
-- Записи и приёмы
-- ----------------------------------------------------------------------------
-- price_kopecks фиксируется на момент записи (снимок цены из service_prices),
-- чтобы смена прайса не меняла смысл ранее оформленных операций.
CREATE TABLE IF NOT EXISTS appointments (
    id            INTEGER PRIMARY KEY,
    animal_id     INTEGER NOT NULL REFERENCES animals(id)  ON DELETE RESTRICT,
    vet_id        INTEGER NOT NULL REFERENCES vets(id)     ON DELETE RESTRICT,
    service_id    INTEGER NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
    appt_date     TEXT NOT NULL CHECK (date(appt_date) IS NOT NULL AND date(appt_date) = appt_date),
    appt_time     TEXT NOT NULL CHECK (appt_time GLOB '[0-2][0-9]:[0-5][0-9]' AND appt_time <= '23:59'),
    status        TEXT NOT NULL DEFAULT 'запланирован'
                  CHECK (status IN ('запланирован', 'подтверждён', 'отменён', 'завершён')),
    price_kopecks INTEGER NOT NULL CHECK (price_kopecks >= 0),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Слот врача (vet_id, appt_date, appt_time) уникален среди неотменённых записей:
-- частичный UNIQUE-индекс, чтобы слот отменённой записи можно было занять снова.
CREATE UNIQUE INDEX IF NOT EXISTS ux_appointments_slot
    ON appointments(vet_id, appt_date, appt_time) WHERE status <> 'отменён';
CREATE INDEX IF NOT EXISTS ix_appointments_date   ON appointments(appt_date);
CREATE INDEX IF NOT EXISTS ix_appointments_status ON appointments(status);
CREATE INDEX IF NOT EXISTS ix_appointments_animal ON appointments(animal_id);

-- visit — фактический приём; создаётся при закрытии записи (транзакция п.6.3).
CREATE TABLE IF NOT EXISTS visits (
    id             INTEGER PRIMARY KEY,
    appointment_id INTEGER NOT NULL UNIQUE REFERENCES appointments(id) ON DELETE RESTRICT,
    diagnosis      TEXT,
    complaints     TEXT,
    closed_at      TEXT
);

CREATE TABLE IF NOT EXISTS medications (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK (length(trim(name)) > 0),
    unit TEXT NOT NULL CHECK (length(trim(unit)) > 0)
);

-- qty — сколько единиц препарата списывается со склада при закрытии приёма.
CREATE TABLE IF NOT EXISTS prescriptions (
    id            INTEGER PRIMARY KEY,
    visit_id      INTEGER NOT NULL REFERENCES visits(id)      ON DELETE CASCADE,
    medication_id INTEGER NOT NULL REFERENCES medications(id) ON DELETE RESTRICT,
    dosage        TEXT NOT NULL CHECK (length(trim(dosage)) > 0),
    course_days   INTEGER CHECK (course_days IS NULL OR course_days > 0),
    qty           INTEGER NOT NULL DEFAULT 1 CHECK (qty > 0)
);
CREATE INDEX IF NOT EXISTS ix_prescriptions_visit ON prescriptions(visit_id);

-- ----------------------------------------------------------------------------
-- Склад
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stock_batches (
    id            INTEGER PRIMARY KEY,
    medication_id INTEGER NOT NULL REFERENCES medications(id) ON DELETE RESTRICT,
    batch_no      TEXT NOT NULL CHECK (length(trim(batch_no)) > 0),
    qty           INTEGER NOT NULL CHECK (qty >= 0),
    expiry_date   TEXT NOT NULL CHECK (date(expiry_date) IS NOT NULL AND date(expiry_date) = expiry_date),
    UNIQUE (medication_id, batch_no)
);
CREATE INDEX IF NOT EXISTS ix_stock_batches_expiry ON stock_batches(expiry_date);

-- Журнал движений: история не удаляется вместе с приёмом (SET NULL), партию
-- с движениями удалить нельзя (RESTRICT).
CREATE TABLE IF NOT EXISTS stock_movements (
    id        INTEGER PRIMARY KEY,
    batch_id  INTEGER NOT NULL REFERENCES stock_batches(id) ON DELETE RESTRICT,
    visit_id  INTEGER REFERENCES visits(id) ON DELETE SET NULL,
    qty_delta INTEGER NOT NULL CHECK (qty_delta <> 0),
    reason    TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    moved_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_stock_movements_batch ON stock_movements(batch_id);

-- ----------------------------------------------------------------------------
-- Оплаты, вакцинации, показатели, напоминания
-- ----------------------------------------------------------------------------
-- Платёж привязан к записи на приём (а не к visit), чтобы клиент мог оплатить
-- заранее — сразу при записи — или в день приёма (полностью или частями).
-- Финансовую историю каскадом не удаляем (RESTRICT).
CREATE TABLE IF NOT EXISTS payments (
    id             INTEGER PRIMARY KEY,
    appointment_id INTEGER NOT NULL REFERENCES appointments(id) ON DELETE RESTRICT,
    amount_kopecks INTEGER NOT NULL CHECK (amount_kopecks >= 0),
    method         TEXT CHECK (method IS NULL OR method IN ('наличные', 'карта', 'перевод')),
    status         TEXT NOT NULL DEFAULT 'ожидает' CHECK (status IN ('ожидает', 'оплачен', 'возврат')),
    paid_at        TEXT,
    CHECK (status <> 'оплачен' OR (method IS NOT NULL AND paid_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_payments_appointment ON payments(appointment_id);

CREATE TABLE IF NOT EXISTS vaccinations (
    id            INTEGER PRIMARY KEY,
    animal_id     INTEGER NOT NULL REFERENCES animals(id)     ON DELETE CASCADE,
    medication_id INTEGER NOT NULL REFERENCES medications(id) ON DELETE RESTRICT,
    vacc_date     TEXT NOT NULL CHECK (date(vacc_date) IS NOT NULL AND date(vacc_date) = vacc_date),
    next_due_date TEXT CHECK (next_due_date IS NULL OR (date(next_due_date) IS NOT NULL AND date(next_due_date) = next_due_date)),
    CHECK (next_due_date IS NULL OR next_due_date > vacc_date),
    UNIQUE (animal_id, medication_id, vacc_date)
);
CREATE INDEX IF NOT EXISTS ix_vaccinations_animal ON vaccinations(animal_id);

CREATE TABLE IF NOT EXISTS vital_signs (
    id          INTEGER PRIMARY KEY,
    visit_id    INTEGER NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
    weight_kg   NUMERIC CHECK (weight_kg IS NULL OR weight_kg > 0),
    temp_c      NUMERIC CHECK (temp_c IS NULL OR temp_c BETWEEN 35 AND 43),
    measured_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (weight_kg IS NOT NULL OR temp_c IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_vital_signs_visit ON vital_signs(visit_id);

CREATE TABLE IF NOT EXISTS reminders (
    id        INTEGER PRIMARY KEY,
    animal_id INTEGER NOT NULL REFERENCES animals(id) ON DELETE CASCADE,
    kind      TEXT NOT NULL CHECK (kind IN ('ревакцинация', 'повторный приём', 'оплата')),
    due_date  TEXT NOT NULL CHECK (date(due_date) IS NOT NULL AND date(due_date) = due_date),
    status    TEXT NOT NULL DEFAULT 'запланировано'
              CHECK (status IN ('запланировано', 'выполнено', 'просрочено')),
    UNIQUE (animal_id, kind, due_date)
);
CREATE INDEX IF NOT EXISTS ix_reminders_due ON reminders(due_date);

-- ----------------------------------------------------------------------------
-- Триггеры целостности (правила ТЗ п.3 на уровне БД)
-- ----------------------------------------------------------------------------
-- Врач должен иметь специализацию, требуемую услугой.
CREATE TRIGGER IF NOT EXISTS trg_appt_specialization_ins
BEFORE INSERT ON appointments
WHEN EXISTS (SELECT 1 FROM services s, vets v
             WHERE s.id = NEW.service_id AND v.id = NEW.vet_id
               AND s.required_specialization IS NOT NULL
               AND s.required_specialization <> v.specialization)
BEGIN
    SELECT RAISE(ABORT, 'Специализация врача не соответствует услуге');
END;

CREATE TRIGGER IF NOT EXISTS trg_appt_specialization_upd
BEFORE UPDATE OF vet_id, service_id ON appointments
WHEN EXISTS (SELECT 1 FROM services s, vets v
             WHERE s.id = NEW.service_id AND v.id = NEW.vet_id
               AND s.required_specialization IS NOT NULL
               AND s.required_specialization <> v.specialization)
BEGIN
    SELECT RAISE(ABORT, 'Специализация врача не соответствует услуге');
END;

-- Допустимые переходы статусов: завершённую и отменённую запись менять нельзя.
CREATE TRIGGER IF NOT EXISTS trg_appt_status_flow
BEFORE UPDATE OF status ON appointments
WHEN OLD.status IN ('завершён', 'отменён') AND NEW.status <> OLD.status
BEGIN
    SELECT RAISE(ABORT, 'Недопустимый переход статуса записи');
END;

-- Сумма платежей по записи (оплаты/ожидания минус возвраты) не больше цены записи.
CREATE TRIGGER IF NOT EXISTS trg_payment_limit_ins
BEFORE INSERT ON payments
WHEN (SELECT COALESCE(SUM(CASE status WHEN 'возврат' THEN -amount_kopecks ELSE amount_kopecks END), 0)
      FROM payments WHERE appointment_id = NEW.appointment_id)
     + CASE NEW.status WHEN 'возврат' THEN -NEW.amount_kopecks ELSE NEW.amount_kopecks END
     > (SELECT price_kopecks FROM appointments WHERE id = NEW.appointment_id)
BEGIN
    SELECT RAISE(ABORT, 'Сумма оплат превышает стоимость приёма');
END;

CREATE TRIGGER IF NOT EXISTS trg_payment_limit_upd
BEFORE UPDATE OF amount_kopecks, status, appointment_id ON payments
WHEN (SELECT COALESCE(SUM(CASE status WHEN 'возврат' THEN -amount_kopecks ELSE amount_kopecks END), 0)
      FROM payments WHERE appointment_id = NEW.appointment_id AND id <> NEW.id)
     + CASE NEW.status WHEN 'возврат' THEN -NEW.amount_kopecks ELSE NEW.amount_kopecks END
     > (SELECT price_kopecks FROM appointments WHERE id = NEW.appointment_id)
BEGIN
    SELECT RAISE(ABORT, 'Сумма оплат превышает стоимость приёма');
END;

-- По отменённой записи можно только вернуть деньги, но не принять новую оплату.
CREATE TRIGGER IF NOT EXISTS trg_payment_cancelled
BEFORE INSERT ON payments
WHEN NEW.status <> 'возврат'
 AND (SELECT status FROM appointments WHERE id = NEW.appointment_id) = 'отменён'
BEGIN
    SELECT RAISE(ABORT, 'Запись отменена: принять оплату нельзя');
END;

-- ----------------------------------------------------------------------------
-- Представления
-- ----------------------------------------------------------------------------
-- Предстоящие/незавершённые приёмы с ФИО врача и кличкой животного.
CREATE VIEW IF NOT EXISTS v_active_appointments AS
SELECT a.id            AS appointment_id,
       a.appt_date,
       a.appt_time,
       a.status,
       a.price_kopecks,
       an.id           AS animal_id,
       an.name         AS animal_name,
       o.full_name     AS owner_name,
       o.phone         AS owner_phone,
       v.id            AS vet_id,
       v.full_name     AS vet_name,
       s.name          AS service_name
FROM appointments a
JOIN animals  an ON an.id = a.animal_id
JOIN owners   o  ON o.id  = an.owner_id
JOIN vets     v  ON v.id  = a.vet_id
JOIN services s  ON s.id  = a.service_id
WHERE a.status IN ('запланирован', 'подтверждён');

-- Завершённые приёмы, по которым оплачено меньше стоимости приёма.
CREATE VIEW IF NOT EXISTS v_debt_visits AS
SELECT vi.id            AS visit_id,
       a.id             AS appointment_id,
       a.appt_date,
       an.id            AS animal_id,
       an.name          AS animal_name,
       o.id             AS owner_id,
       o.full_name      AS owner_name,
       o.phone          AS owner_phone,
       a.price_kopecks,
       COALESCE(p.paid, 0)                   AS paid_kopecks,
       a.price_kopecks - COALESCE(p.paid, 0) AS debt_kopecks
FROM visits vi
JOIN appointments a  ON a.id  = vi.appointment_id
JOIN animals      an ON an.id = a.animal_id
JOIN owners       o  ON o.id  = an.owner_id
LEFT JOIN (SELECT appointment_id,
                  SUM(CASE status WHEN 'оплачен' THEN amount_kopecks
                                  WHEN 'возврат' THEN -amount_kopecks ELSE 0 END) AS paid
           FROM payments GROUP BY appointment_id) p ON p.appointment_id = a.id
WHERE a.status = 'завершён'
  AND a.price_kopecks - COALESCE(p.paid, 0) > 0;

-- Ближайшая ревакцинация животного: по каждому препарату берётся последняя
-- вакцинация, из её next_due_date — минимальная дата.
CREATE VIEW IF NOT EXISTS v_animal_revaccination AS
SELECT v.animal_id, MIN(v.next_due_date) AS next_due_date
FROM vaccinations v
WHERE v.next_due_date IS NOT NULL
  AND v.vacc_date = (SELECT MAX(v2.vacc_date) FROM vaccinations v2
                     WHERE v2.animal_id = v.animal_id AND v2.medication_id = v.medication_id)
GROUP BY v.animal_id;
