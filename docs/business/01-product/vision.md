# Product Vision & Value Proposition

> **Актуально:** Hardware-first модель. IMU-трекеры = основной продукт. SkateLab SaaS = AI-платформа для анализа.

## Mission

SkateLab — система трекеров для фигурных коньков с AI-платформой.

Точные метрики техники: угол ребра, скорость вращения, биомеханика прыжков. Объективные данные вместо догадок.

## Problem Statement

Фигуристы и тренеры сталкиваются с тремя проблемами:

1. **Нет объективных данных.** Оценка техники — субъективное восприятие тренера. Нет числовых метрик: угол ребра, скорость вращения, высота прыжка.
2. **Дорого.** Биомеханический анализ доступен только национальным сборным (Omega — 14 камер, закрытый софт). Индивидуальные фигуристы и малые клубы — без доступа.
3. **Языковой барьер.** Существующие решения — на английском. Русскоязычные фигуристы (Россия, Казахстан, Беларусь) не получают анализа на родном языке.

## Value Proposition

**Для тренеров:** IMU-трекеры на коньках ученика → точные метрики на русском. Объективные данные для корректировки техники.

**Для спортсменов:** Узнай, что не так с твоим прыжком. Угол ребра, GOE proxy, сравнение с эталоном.

**Для клубов:** Единая система аналитики. Масштабирование качества тренерской работы.

## Unique Differentiators

| Дифференциатор | Что это | Почему важно |
|---------------|---------|-------------|
| IMU + AI гибрид | Датчики на коньках + видео-аналитика | Точнее video-only (±1° vs ±10°) |
| OOFSkate proxy features | Оценка качества через кинематику тела | Работает даже без IMU |
| CoM trajectory | Центр масс вместо времени полёта | Устраняет 60% ошибку в высоте прыжка |
| Русский язык | Полная локализация: UI, рекомендации, метрики | Единственный продукт с native русским |
| Хореограф-планировщик | ISU element DB + CSP solver + music analysis | Визуальное планирование программы |
| Цена | 15 500 ₽ vs $600–2000+ (wearable market) | Доступно индивидуальным спортсменам |

## Product Components

### Hardware

| Компонент | Описание |
|-----------|----------|
| IMU-трекеры (2 шт) | Toe + heel, угол наклона ребра, ускорение |
| Крепление | Липучка с EVA-прокладкой / 3D-printed кейс |
| Зарядка | USB-C, до 4 часов работы |
| Mobile app | Android (Kotlin), BLE 5.0, real-time data |

### SkateLab AI Platform

| Компонент | Описание |
|-----------|----------|
| Upload | Chunked S3 multipart upload, presigned URLs |
| Sessions | CRUD с метриками, персистенция в Postgres |
| Metrics Registry | 12+ биомеханических метрик, русские лейблы |
| Progress Dashboard | Тренды, PR трекер, диагностика |
| Coach Dashboard | Ученики, сессии, диагностика |
| Choreography Planner | ISU elements + CSP solver + SVG rink |

### Tech Stack

| Слой | Технология |
|------|-----------|
| Hardware | IMU (BNO085), BLE 5.0, Kotlin Android |
| ML Pipeline | Python, onnxruntime-gpu, scipy, numba |
| Backend | FastAPI, SQLAlchemy, arq + Valkey |
| Frontend | Next.js 16, React, Tailwind, shadcn/ui |
| Storage | Cloudflare R2, Postgres |
| Remote GPU | Vast.ai Serverless |

## Current Status

**MVP hardware + software в разработке.**

- Mobile app: Android (Kotlin), BLE data collection ✅
- IMU experiments: Кронверкский пр., угол ребра реконструирован ✅
- AI-платформа: ~279 тест-кейсов, pipeline ~12s. ⚠️ Тесты не все проходят (1 ошибка при сборке).
- 3D-printed кейс: в разработке (ИТМО)

## Key Constraints

- **GPU-only inference.** CPU запрещена. `device='cuda'`.
- **Backend не импортирует ML internals.** arq worker только диспетчер.
- **Hardware dependency.** IMU-трекеры требуют IMU + mobile app.
