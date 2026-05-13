# Skating Biomechanics ML

[![CI](https://github.com/Artiffusion-Inc/skatelab/actions/workflows/ci.yml/badge.svg?branch=master&label=CI)](https://github.com/Artiffusion-Inc/skatelab/actions)
[![codecov](https://codecov.io/github/Artiffusion-Inc/skatelab/graph/badge.svg?token=0QK5TTR8QZ)](https://codecov.io/github/Artiffusion-Inc/skatelab)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](https://github.com/Artiffusion-Inc/skatelab/pulls)

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Litestar](https://img.shields.io/badge/Litestar-2.x%2B-EDDA7A?logo=python&logoColor=black)](https://litestar.dev)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=nextdotjs&logoColor=white)](https://nextjs.org)
[![CUDA](https://img.shields.io/badge/CUDA-GPU-76B900?logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-zone)

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![basedpyright](https://img.shields.io/badge/basedpyright-checked-blue?logo=python&logoColor=white)](https://github.com/detachhead/basedpyright)
[![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com)

AI-тренер по фигурному катанию — анализ видео, сравнение с эталонами, биомеханическая обратная связь на русском.

## Quick Start

```bash
uv sync
bash ml/scripts/setup_cuda_compat.sh   # CUDA GPU setup (RTX 3050 Ti)

# Анализ видео (ML pipeline)
cd ml && uv run python -m src.cli analyze video.mp4 --element waltz_jump --pose-backend rtmlib

# Сравнение двух видео (тренировочный режим)
cd ml && uv run python -m src.cli compare attempt.mp4 reference.mp4 --overlays skeleton,angles,timer

# Визуализация с 3D-коррекцией скелета
cd ml && uv run python scripts/visualize_with_skeleton.py video.mp4 --layer 2 --3d --output out.mp4
```

## Architecture

```
Video → RTMPose (rtmlib, CUDA) → HALPE26 (26kp) → H3.6M (17kp)
  → GapFiller → Smoothing → [Optional] CorrectiveLens (3D→2D correction)
  → Phase Detection → Biomechanics Metrics → DTW → Recommender → Russian Report
```

| Component | Technology |
|-----------|-----------|
| **2D Pose** | RTMPose via rtmlib (HALPE26, 26kp, CUDA) |
| **3D Lifting** | MotionAGFormer-S / Biomechanics3DEstimator |
| **3D Correction** | CorrectiveLens (kinematic constraints + anchor projection) |
| **Tracking** | OC-SORT + anatomical biometric Re-ID |
| **Physics** | CoM trajectory, Dempster anthropometric tables |
| **GPU** | CUDA via onnxruntime-gpu (7.1x speedup) |

## Business Validation Status

> **Обновлено:** 2026-05-13. Аудит бизнес-документации.

### CustDev

| Сегмент | Интервью | Статус |
|---------|----------|--------|
| Тренеры (A1) | 2 | ✅ Подтверждена боль (субъективность оценки, споры с учениками). WTP условный («если докажут»). |
| Спортсмены (A2) | 1 | ✅ Подтверждена боль (медленный прогресс). WTP до 10K разово, 500–600 ₽/мес. |
| Хореографы (B1) | 0 | ⚠️ Боль описана, но не валидирована. Цифры «5–10 часов» — с потолка. |
| Родители (B2) | 0 | ⚠️ Боль правдоподобна, но WTP не подтверждена. 35K/мес — стоимость тренировок, не ущерб от отсутствия данных. |
| Клубы (C2) | 0 | ❌ Hold. Боль «отток из-за аналитики» — надуманна. CustDev = 0. |
| Федерации (D1) | 0 | ❌ Рано. «Ущерб высокий, но не осознают» — противоречие. |

### Pricing (невалидированные гипотезы)

| Продукт | Цена | Источник | Валидация |
|---------|------|----------|-----------|
| Individual hardware | TBD (оценка: 8–12K ₽) | Cost-plus | ❌ Никто не называл цену |
| SaaS Entry | 490 ₽/мес | Оценка | ⚠️ Вписан в WTP спортсмена |
| SaaS Pro | 990 ₽/мес | Оценка | ❌ **Выше WTP 500–600 ₽/мес** |
| SaaS Coach | 1 500–3 500 ₽/мес | Оценка | ❌ Тренер WTP = «если докажут» |

**Единственная валидированная цифра:** WTP спортсмена 500–600 ₽/мес + до 10 000 ₽ разово (1 респондент).

**BOM:** ~3 230 ₽/комплект. Cost-плюс наценка 3x = 9 690 ₽ (вписан в WTP до 10K).

### Critical Gaps (P0)

1. **Прототип не тестирован с реальными пользователями** — CustDev был без прототипа
2. **Нет валидации точности ML** — нет бенчмарка против ground truth
3. **Pro tier превышает WTP** — 990₽ > 500–600₽ WTP спортсмена

Подробности: `docs/business/04-financial/unit-economics.md`, `docs/business/02-market/abcd-segmentation.md`

## Project Structure

```
skatelab/
├── backend/               # Litestar API server
│   ├── app/               # Python package (backend.app.*)
│   ├── tests/             # Backend tests
│   └── pyproject.toml     # Backend dependencies
├── frontend/              # Next.js 16 app
│   ├── app/               # App router pages
│   ├── components/        # React components
│   ├── lib/               # API client, hooks, utils
│   └── pyproject.toml     # Frontend dependencies (bun)
├── ml/                    # ML pipeline (pure library)
│   ├── src/               # Python package (src.*)
│   ├── tests/             # ML tests
│   ├── scripts/           # Standalone scripts
│   └── pyproject.toml     # ML dependencies
├── docs/                  # Documentation
│   ├── business/          # Business knowledge base
│   ├── research/          # Research findings
│   ├── plans/             # Implementation plans
│   └── specs/             # Design documents
├── infra/                 # Infrastructure (Containerfile, Caddyfile)
├── data/                  # Data files (datasets, references)
└── experiments/           # Jupyter notebooks
```

## Research

See [`docs/research/RESEARCH.md`](docs/research/RESEARCH.md) — index of all research materials, memory bank.

## Quality

```bash
# Tests
uv run pytest backend/tests/ ml/tests/ -v -m "not slow"

# Lint
uv run ruff check backend/ ml/
uv run ruff format backend/ ml/

# Type check
uv run basedpyright --level error backend/app ml/src
```

## License

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)