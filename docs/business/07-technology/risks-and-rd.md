# Technology & R&D Risks

> **Актуально:** Hardware-first модель (IMU-трекеры). SaaS — дополнительный поток.

## Current Tech Stack

| Компонент | Технология | Версия | Зрелость |
|-----------|-----------|--------|----------|
| **IMU Hardware** | **IMU (MPU9250), BLE 5.0** | — | **Prototype** |
| Mobile App (Hardware) | Kotlin, Android | Latest | WIP (`mobile/lib/`) |
| ML Pipeline | Python, rtmlib, onnxruntime-gpu | 3.12, latest | MVP complete |
| Pose Backend | RTMO/Body (COCO 17kp) | rtmlib latest | Production-ready |
| 3D Lifter | MotionAGFormer-S | 59MB | Functional |
| Backend | FastAPI, SQLAlchemy, Alembic | Latest | Production-ready |
| Frontend | Next.js 16, React, Tailwind | Latest | MVP complete |
| Database | Postgres | 16 | Stable |
| Task Queue | arq + Valkey | Latest | Functional |
| Storage | Cloudflare R2 | — | Stable |
| Remote GPU | Vast.ai Serverless | — | Functional |

## R&D Roadmap

### Completed (MVP Software)

- ✅ RTMO pose estimation pipeline (~12s for 14.5s video)
- ✅ CoM-based phase detection (eliminates 60% height error)
- ✅ OOFSkate proxy features (landing quality, GOE proxy)
- ✅ Anatomical Re-ID (solves black clothing on ice)
- ✅ Choreography planner (CSP solver, music analysis)
- ✅ 3D skeleton viewer (three.js)
- ✅ Side-by-side comparison
- ✅ Rate limiting, caching, i18n

### In Progress / Planned (Hardware)

| Фича | Приоритет | Сложность | Статус |
|------|-----------|-----------|--------|
| **3D-printed кейс для IMU** | **High** | Medium | **В разработке (ИТМО)** |
| **Mobile app BLE integration** | **High** | High | **WIP (`mobile/lib/`)** |
| **IMU + video sync** | **High** | High | **PoC** |
| GCN element classifier | Medium | High | Research |
| Reference database expansion | High | Medium | Planned |
| Real-time pipeline (<1s) | Low | Very High | Research |

## Technical Risks

### HIGH Risk

| Риск | Вероятность | Влияние | Mitigation |
|------|-----------|---------|-----------|
| **Hardware production (IMU + кейс)** | **Высокая** | **Высокое** | **3D-printed прототип (ИТМО), локальные поставщики** |
| **IMU калибровка и точность** | **Высокая** | **Высокое** | **MPU9250 (±1° в статике, динамика TBD), калибровка per-unit, firmware updates** |
| **GPU cost scaling** | Высокая | Высокое | Vast.ai spot, on-device inference, model quantization |
| **Dataset licensing** | Высокая | Высокое | Audit all licenses, obtain commercial where needed |
| **Single-camera blade detection** | Certain | Высокое | OOFSkate proxy features + IMU hybrid |

### MEDIUM Risk

| Риск | Вероятность | Влияние | Mitigation |
|------|-----------|---------|-----------|
| BLE connectivity (on ice) | Средняя | Среднее | BLE 5.0, кэширование, offline mode |
| R2/Cloudflare outage | Низкая | Среднее | Multi-cloud fallback (Hetzner S3) |
| 152-ФЗ compliance | Высокая | Среднее | Russian hosting for PII, R2 for media only |
| Seasonal demand spikes | Высокая | Среднее | Auto-scaling GPU via Vast.ai, pre-warm |

### LOW Risk

| Риск | Вероятность | Влияние | Mitigation |
|------|-----------|---------|-----------|
| ONNX Runtime deprecation | Низкая | Низкое | Pin versions, test upgrades |
| Next.js major version break | Низкая | Низкое | Pin version, gradual upgrades |
| Vast.ai availability | Средняя | Низкое | Local GPU fallback (RTX 3050 Ti) |

## IMU Hardware

> **Статус:** Прототип. Алиса проводит тесты на льду.

### Current Findings

- IMU прикреплён к коньку (toe + heel positions)
- Реконструирован угол наклона ребра через отношение бокового/вертикального ускорения (1 датчик)
- Крепление: липучка с EVA-прокладкой (прототип)
- 3D-printed кейс — в разработке (ИТМО)
- **Потенциальная интеграция:** IMU trajectory + 2D→3D skeleton → полная 3D реконструкция

### BOM (Bill of Materials)

| Компонент | Стоимость (₽) | Примечание |
|-----------|--------------|-----------|
| IMU датчик WitMotion WT901 BLE CL (2 шт) | 1 441 × 2 = 2 882 | Озон, включая Type-C зарядку |
| Крепление (липучка/EVA) | ~150 | Прототип |
| 3D-printed кейс | TBD | ИТМО |
| Bluetooth модуль | Вкл. в IMU | BLE 5.0 |
| Зарядка (USB-C) | Вкл. в IMU | — |
| **Итого BOM (только компоненты)** | **~3 030 ₽** | 2 882 (IMU) + 150 (крепление), без упаковки/логистики |

### Hardware Risks

- Крепление на льду: вибрация, влажность, удары
- Синхронизация IMU ↔ video timestamps
- Калибровка: каждый датчик нужно калибровать
- BLE range: ~10m, может не хватить на катке

## GPU Cost Model

### Cost Optimization (2026-05-05)

GPU cost снижен с $0.5/час до $0.01/час (50x). Достаточно GTX 1070 Ti.

### Current Performance

| Видео | Pipeline время | GPU тип | Стоимость |
|-------|---------------|---------|-----------|
| 14.5s (frame_skip=8) | ~12s | RTX 4090 | ~$0.03 |
| 30s (frame_skip=4) | ~25s | RTX 4090 | ~$0.06 |
| 60s (frame_skip=4) | ~50s | RTX 4090 | ~$0.12 |

### Scale Projections

| Пользователей | Анализов/мес | GPU cost/мес | GPU cost/год |
|-------------|-------------|-------------|-------------|
| 100 | 1,000 | $30–60 | $360–720 |
| 500 | 5,000 | $150–300 | $1,800–3,600 |
| 2,000 | 20,000 | $600–1,200 | $7,200–14,400 |

### Mitigation

1. **On-device inference** — Mobile GPU (Adreno, Apple Neural Engine)
2. **Model quantization** — INT8/FP16 RTMO reduces inference time 2x
3. **Frame skip tuning** — Already using frame_skip=8
4. **Batch processing** — Queue during off-peak for lower Vast.ai spot prices
5. **Caching** — Same video → cached results

## R&D Budget Allocation

| Категория | Доля | Приоритет |
|-----------|------|-----------|
| **Hardware (IMU + кейс)** | **35%** | **Highest** |
| **Mobile app (BLE)** | **25%** | **High** |
| ML accuracy improvement | 20% | High |
| Infrastructure reliability | 10% | Medium |
| New features (choreography) | 10% | Medium |

## Key Research Papers

1. **OOFSkate (MIT, 2026)** — Body kinematics proxy features, deployed at Olympics
2. **RTMO (OpenMMLab)** — Current pose backbone, Apache 2.0
3. **MotionAGFormer** — 3D lifter, AthletePose3D
4. **FSBench (CVPR 2025)** — 783 videos, benchmark for figure skating
5. **YourSkatingCoach (2024)** — BIOES-tagging for element boundaries
6. **Pose2Sim (592 stars)** — 2D→3D→OpenSim pipeline
7. **HSMR (608 stars)** — CVPR25 Oral, biomechanically accurate 3D
