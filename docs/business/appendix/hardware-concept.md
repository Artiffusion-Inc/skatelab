# Hardware — Основной Продукт

> **Актуально:** Hardware-first модель. IMU-трекеры = основной продукт. SkateLab SaaS = AI-платформа.
> **Источник:** Наброски Алисы Абдуллиной (ITMO, СПб).

## Концепция

**IMU hardware** — IMU-датчики (toe + heel) на ботинках фигуриста + мобильное приложение с AI-аналитикой.

### Названия
- **IMU hardware** — hardware (IMU-трекеры)
- **SkateLab** — SaaS / AI-платформа

## IMU Experiments (2026-05-04)

**Место:** Ледовая арена (вечерние часы)

**Результаты:**
- IMU прикреплён к коньку
- Реконструирован угол наклона ребра через отношение бокового → вертикального ускорения (1 датчик)
- Результаты правдоподобные
- Крепление: липучка с EVA-прокладкой (прототип)
- 3D-printed кейс — в разработке (ИТМО)

## Product Specs

### Hardware

| Компонент | Спецификация |
|-----------|-------------|
| Датчики | 2 IMU (toe + heel), WitMotion WT901 BLE CL |
| BLE | 5.0, real-time data transfer |
| Крепление | Липучка с EVA / 3D-printed кейс |
| Зарядка | USB-C |
| Время работы | До 4 часов |

### Software

| Компонент | Описание |
|-----------|----------|
| Mobile app | Android (Kotlin), BLE pairing, real-time metrics |
| Cloud sync | Автозагрузка сессий, аналитика |
| Web dashboard | Coach dashboard, прогресс, сравнение |

## Pricing

| Сегмент | Продукт | Цена (₽) |
|---------|---------|---------|
| **Тренеры / спортсмены** | **Individual (2 IMU + крепление + зарядка)** | **TBD** |
| Академии | Pro (проф клубы) | TBD |
| Pro coaches | Coach (3–5 athlete sets) | TBD |
| Schools / Academies | Academy (групповой + планшет) | TBD |
| Федерации | Custom + Analytics | TBD |

## Integration with SkateLab

| IMU Hardware | SkateLab |
|-----------|----------|
| IMU data (углы ребра, ускорение) | Видео-аналитика (биомеханика) |
| Real-time on-ice | Post-session deep analysis |
| Hardware revenue | Subscription revenue |
| Точность ±1° (IMU) | Точность ±10° (video-only) |

## Pain Points

| Pain | Решение IMU hardware |
|------|-------------------|
| Стоимость тренировок 15–35K ₽/мес | Объективные данные → меньше времени на разбор |
| Время разбора ошибок (1/3 тренировки) | Real-time метрики на коньках |
| Субъективность оценки ребра ±10–15° | IMU: точный угол наклона |
| Тренер-ученик конфликты | Объективные данные → нет споров |

## Business Model

**Hardware-first:** IMU-трекеры = основной продукт (цена TBD).
**SaaS-second:** SkateLab = дополнительная прибыль (490–990 ₽/мес).

**Unit economics:**
- VC ~3 030 ₽ (2× WT901 2 882 ₽ + крепление ~150 ₽)
- Налог УСН 15%: TBD (зависит от цены продажи)
- Итого VC с налогом: TBD
- Маржа: TBD
- Break-even: TBD

## Pilot Program

- 1 мес бесплатного использования
- Priority support
- 50% скидка на первый год
- Контакт: @alyssaabdullina
