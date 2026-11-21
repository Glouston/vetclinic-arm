-- ============================================================================
-- Содержательные SQL-запросы АРМ ветклиники (ТЗ п.7). Параметры: :имя.
-- Для каждого: ID, назначение, параметры, результат, место в приложении.
-- Проверка: python tools/check_queries.py  (выполняет все запросы на seed.sql)
-- ============================================================================

-- ---------- Выборки с условиями и сортировкой --------------------------------
-- Q01 | Поиск животных по кличке/владельцу/телефону с фильтрами вида и пола.
-- Параметры: :s (шаблон LIKE или NULL), :species, :sex (или NULL), :today.
-- Результат: кличка, вид, владелец, телефон, ближайшая ревакцинация, статус (светофор).
-- Где: раздел «Животные» (clients.list_animals); фильтры применяются совместно.
SELECT an.name, an.species, o.full_name, o.phone, r.next_due_date,
       CASE WHEN r.next_due_date IS NULL THEN 'нет данных'
            WHEN r.next_due_date < :today THEN 'просрочена'
            WHEN r.next_due_date <= date(:today, '+30 days') THEN 'скоро' ELSE 'в норме' END AS status
FROM animals an
JOIN owners o ON o.id = an.owner_id
LEFT JOIN v_animal_revaccination r ON r.animal_id = an.id
WHERE (:s IS NULL OR an.name LIKE :s OR o.full_name LIKE :s OR o.phone LIKE :s)
  AND (:species IS NULL OR an.species = :species)
  AND (:sex IS NULL OR an.sex = :sex)
ORDER BY an.name;

-- Q02 | Записи за период с фильтром по статусу и врачу, по возрастанию даты/времени.
-- Параметры: :df, :dt, :status, :vet (необязательные). Где: раздел «Записи на приём».
SELECT a.appt_date, a.appt_time, an.name AS animal, v.full_name AS vet, s.name AS service, a.status, a.price_kopecks
FROM appointments a
JOIN animals an ON an.id = a.animal_id
JOIN vets v ON v.id = a.vet_id
JOIN services s ON s.id = a.service_id
WHERE a.appt_date BETWEEN :df AND :dt
  AND (:status IS NULL OR a.status = :status)
  AND (:vet IS NULL OR a.vet_id = :vet)
ORDER BY a.appt_date, a.appt_time;

-- ---------- Соединение таблиц ----------------------------------------------------
-- Q03 | История приёмов животного: 5 таблиц (appointments, vets, services, visits, animals).
-- Параметр: :animal_id. Результат: дата, врач, услуга, диагноз. Где: карточка животного, вкладка «Приёмы».
SELECT a.appt_date, v.full_name AS vet, s.name AS service, vi.diagnosis, a.status
FROM appointments a
JOIN vets v ON v.id = a.vet_id
JOIN services s ON s.id = a.service_id
LEFT JOIN visits vi ON vi.appointment_id = a.id
WHERE a.animal_id = :animal_id
ORDER BY a.appt_date DESC;

-- Q04 | Назначения животного с названием препарата и врачом (JOIN 6 таблиц).
-- Параметр: :animal_id. Где: карточка животного, вкладка «Назначения»; печатная форма «Назначение лечения».
SELECT a.appt_date, m.name AS medication, p.dosage, p.course_days, p.qty, m.unit, v.full_name AS vet
FROM prescriptions p
JOIN visits vi ON vi.id = p.visit_id
JOIN appointments a ON a.id = vi.appointment_id
JOIN medications m ON m.id = p.medication_id
JOIN vets v ON v.id = a.vet_id
WHERE a.animal_id = :animal_id
ORDER BY a.appt_date DESC, p.id;

-- Q05 | Партии склада с препаратом и статусом срока годности (JOIN 2 таблиц + CASE).
-- Параметры: :today, :days (NULL — без фильтра «истекает в течение N дней»).
-- Где: раздел «Склад».
SELECT m.name, b.batch_no, b.qty, b.expiry_date,
       CASE WHEN b.expiry_date < :today THEN 'просрочен'
            WHEN b.expiry_date <= date(:today, '+30 days') THEN 'истекает' ELSE 'в норме' END AS state
FROM stock_batches b
JOIN medications m ON m.id = b.medication_id
WHERE :days IS NULL OR (b.expiry_date >= :today AND b.expiry_date <= date(:today, '+' || :days || ' days'))
ORDER BY m.name, b.expiry_date;

-- ---------- Агрегирование и группировка --------------------------------------------
-- Q06 | Выручка по врачам и услугам за период (GROUP BY). Параметры: :f, :t, :c (категория или NULL).
-- Выручка = оплаченное (включая предоплату) минус возвраты, по дате оплаты, границы включены. Где: сводный отчёт.
SELECT v.full_name AS vet, s.name AS service, COUNT(DISTINCT a.id) AS paid_appointments,
       SUM(CASE pay.status WHEN 'оплачен' THEN pay.amount_kopecks ELSE -pay.amount_kopecks END) AS revenue_kopecks
FROM payments pay
JOIN appointments a ON a.id = pay.appointment_id
JOIN vets v ON v.id = a.vet_id
JOIN services s ON s.id = a.service_id
WHERE pay.status IN ('оплачен', 'возврат') AND date(pay.paid_at) BETWEEN :f AND :t
  AND (:c IS NULL OR s.category = :c)
GROUP BY v.id, s.id
ORDER BY v.full_name, revenue_kopecks DESC;

-- Q07 | Врачи с загрузкой: число завершённых приёмов и средний чек; HAVING — только врачи с ≥ :min приёмами.
-- Параметр: :min. Где: аналитика по врачам (отчёты, защита).
SELECT v.full_name, COUNT(*) AS done_visits, ROUND(AVG(a.price_kopecks) / 100.0, 2) AS avg_check_rub
FROM appointments a
JOIN vets v ON v.id = a.vet_id
WHERE a.status = 'завершён'
GROUP BY v.id
HAVING COUNT(*) >= :min
ORDER BY done_visits DESC;

-- ---------- Подзапрос / CTE -------------------------------------------------------------
-- Q08 | Проблемные животные: CTE разделяет два независимых критерия (просроченная ревакцинация и долг
-- старше N дней), затем объединяет их; в одном SELECT без CTE пришлось бы дублировать агрегаты.
-- Параметры: :d (контрольная дата), :n (порог, дней). Где: проблемный отчёт.
WITH overdue AS (
    SELECT animal_id, next_due_date FROM v_animal_revaccination WHERE next_due_date < :d),
debts AS (
    SELECT animal_id, SUM(debt_kopecks) AS debt FROM v_debt_visits
    WHERE julianday(:d) - julianday(appt_date) > :n GROUP BY animal_id)
SELECT an.name, o.full_name, od.next_due_date, db.debt
FROM animals an
JOIN owners o ON o.id = an.owner_id
LEFT JOIN overdue od ON od.animal_id = an.id
LEFT JOIN debts db ON db.animal_id = an.id
WHERE od.animal_id IS NOT NULL OR db.animal_id IS NOT NULL
ORDER BY an.name;

-- ---------- Поиск отсутствующих связей (NOT EXISTS) --------------------------------------------
-- Q09 | Животные, у которых не было ни одной записи на приём (их можно удалить без потери истории).
-- Где: контроль данных, демонстрация допустимого DELETE (см. Q15).
SELECT an.id, an.name, o.full_name
FROM animals an
JOIN owners o ON o.id = an.owner_id
WHERE NOT EXISTS (SELECT 1 FROM appointments a WHERE a.animal_id = an.id);

-- Q10 | Владельцы без животных. Где: чистка справочника «Владельцы».
SELECT o.id, o.full_name, o.phone
FROM owners o
WHERE NOT EXISTS (SELECT 1 FROM animals an WHERE an.owner_id = o.id);

-- ---------- Представления ------------------------------------------------------------------------
-- Q11 | Предстоящие приёмы на ближайшие дни через VIEW v_active_appointments. Параметр: :today.
-- Где: дашборд «Ближайшие приёмы».
SELECT appt_date, appt_time, animal_name, vet_name, service_name, status
FROM v_active_appointments
WHERE appt_date >= :today
ORDER BY appt_date, appt_time
LIMIT 10;

-- Q12 | Долги: завершённые приёмы без полной оплаты через VIEW v_debt_visits, старейшие первыми.
-- Где: плитка «Ожидают оплаты», напоминания об оплате.
SELECT owner_name, animal_name, appt_date, price_kopecks, paid_kopecks, debt_kopecks
FROM v_debt_visits
ORDER BY appt_date;

-- Q13 | Динамика веса животного (график). Параметр: :animal_id. Где: вкладка «Динамика веса».
SELECT a.appt_date, vs.weight_kg
FROM vital_signs vs
JOIN visits vi ON vi.id = vs.visit_id
JOIN appointments a ON a.id = vi.appointment_id
WHERE a.animal_id = :animal_id AND vs.weight_kg IS NOT NULL
ORDER BY a.appt_date;

-- ---------- Изменение данных ---------------------------------------------------------------------------
-- Q14 | INSERT: новая запись на приём; цена фиксируется из действующей версии service_prices.
-- Параметры: :animal_id, :vet_id, :service_id, :d, :t, :today. Где: диалог «Новая запись».
INSERT INTO appointments (animal_id, vet_id, service_id, appt_date, appt_time, status, price_kopecks)
SELECT :animal_id, :vet_id, :service_id, :d, :t, 'запланирован', p.price_kopecks
FROM service_prices p
WHERE p.service_id = :service_id AND p.valid_from <= :today AND (p.valid_to IS NULL OR p.valid_to >= :today);

-- Q15 | UPDATE: списание из партии с защитой от ухода в минус (атомарно); rowcount = 0 -> ROLLBACK.
-- Параметры: :qty, :batch_id. Где: закрытие приёма (FIFO) и ручное списание на складе.
UPDATE stock_batches SET qty = qty - :qty WHERE id = :batch_id AND qty >= :qty;

-- Q16 | DELETE: только разрешённая запись — животное без истории приёмов (RESTRICT не даст удалить остальные).
-- Параметр: :animal_id. Где: карточка животного, кнопка «Удалить».
DELETE FROM animals
WHERE id = :animal_id
  AND NOT EXISTS (SELECT 1 FROM appointments a WHERE a.animal_id = animals.id);
