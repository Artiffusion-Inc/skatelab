# Appendix: EdgeSense Concept (Alisa Abdullina)

> Источник: наброски Алисы Абдуллиной (ITMO, СПб). Концепция IMU-датчиков + AI для фигурного катания.

## Концепция

**EdgeSense** — IMU-датчики (toe + heel) на ботинках фигуриста + мобильное приложение с AI-аналитикой.

### Варианты названия (обсуждались)
- EdgeSense
- SkateLab / AIceCoach (шуточный вариант)
- Окончательное: **SkateLab** для SaaS, **EdgeSense** для hardware component

### IMU Experiments (2026-05-04)

**Место:** Кронверкский пр., Туполевская 4 (лед доступен после 23:00, безлимитно)

**Результаты:**
- IMU датчик прикреплён к коньку
- Удалось реконструировать угол наклона ребра через отношение бокового → вертикального ускорения (1 датчик)
- Результаты правдоподобные
- Крепление: липучка с EVA-прокладкой (прототип), планируется 3D-printed кейс
- Возможна 3D-печать кейса в ИТМО

### Ключевые идеи (интегрированы в SkateLab)

| Идея EdgeSense | Реализация в SkateLab |
|---------------|----------------------|
| Blade edge detection (IMU) | OOFSkate proxy features (video-based, no hardware) |
| Element recognition | Phase detection + GCN classifier (planned) |
| Real-time feedback | Video analysis ~12s, real-time planned |
| B2B sales model | Subscription SaaS + pilot programs |
| Coach dashboard | ✅ Already implemented |

### Что НЕ интегрировано (hardware-dependent)

- IMU датчики (2 шт: toe + heel) — нужна разработка hardware
- Bluetooth data transfer — аппаратная часть
- Charging station — hardware
- < ±1° accuracy claim — не достижимо с видео-only (OOFSkate: body kinematics proxy)

## Pain Points (из EdgeSense)

| Pain | Оцифровка | Решение SkateLab |
|------|----------|----------------|
| Стоимость тренировок | 15–35K ₽/мес/фигурист | Объективные данные → меньше времени на разбор ошибок |
| Время разбора ошибок | 1/3 тренировки | 12-секундный анализ вместо 10–60 мин ручного |
| Субъективность | ±10–15° ошибка оценки ребра | GOE proxy 0–10, объективные метрики |
| Тренер-ученик конфликты | — | Объективные данные → нет споров |

## Бизнес-модель EdgeSense (B2B)

| Сегмент | Продукт | Цена (₽) |
|---------|---------|---------|
| Schools / Academies | Group set + Tablet + Training | 250K–500K |
| Pro Coaches | Set for 3–5 athletes | 80K–150K |
| Elite Athletes | Individual set (2 sensors + software) | 30K–60K |
| Federations | Custom + Analytics | от 500K |

> **SkateLab позиционирование:** SaaS-подписка без hardware. EdgeSense IMU — потенциальное будущее дополнение (X-сегмент).

## Pitch Draft (Alisa, 2026-05-06)

> Используется для ITMO Startup Night

**Intro:** Меня зовут Алиса, я мастер спорта по фигурному катанию с 16-летним опытом. А я Михаил, также занимаюсь фигурным катанием и отвечаю за техническую сторону.

**Суть:** Мы объединили две сферы — любимый спорт и IT. Создали помощника для фигуристов любого уровня от профи до любителей. Наша платформа позволяет загружать видеоролики с тренировок, анализировать их с помощью AI, давать обратную связь, фиксировать прогресс. Также используем датчики (показываем), которые крепятся на конёк. С их помощью определяем точный угол наклона конька, скорость движения, распознаём элементы, считаем обороты.

**Цель:** Сделать фигурное катание более объективным, помочь спортсменам быстрее прогрессировать, снизить финансовые издержки на тренировки.

## Сравнение: EdgeSense vs SkateLab

| Аспект | EdgeSense | SkateLab |
|--------|-----------|----------|
| Hardware | IMU датчики (2 шт) | Нет (только видео) |
| Точность blade edge | ±1° (IMU) | Proxy features (body kinematics) |
| Точность общая | ±1° (blade) | ±10° (video-based) |
| Scalability | Нужна разработка hardware | SaaS, мгновенный старт |
| Цена входа | 30K–60K ₽ (hardware) | 0 ₽ (freemium) |
| Целевой сегмент | B2B (школы, тренеры) | B2C + B2B |
| Russian language | ✅ (план) | ✅ (реализовано) |
| Coach dashboard | ✅ (план) | ✅ (реализовано) |
| Choreography | ❌ | ✅ (CSP solver) |
| Timeline | Q2-Q3 2026 MVP (hardware) | MVP 100% complete |

## Pilot Program (EdgeSense)

- 1 мес бесплатного использования
- Priority support
- 50% скидка на первый год
- Контакт: @alyssaabdullina