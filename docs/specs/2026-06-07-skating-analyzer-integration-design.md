# SkateLab — Интеграция идей из skating-AI-analyzer

## Цель
Перенести проверенные идеи из проекта skating-AI-analyzer в SkateLab: многомерный скоринг, MVP-геймификация и улучшенное фазовое определение. LLM-vision используется только для разработки и валидации, не в продакшене.

## Мотивация
- Текущий GOE proxy score — единственное число 0-10, недостаточно информативен для тренера и спортсмена
- Фазовое определение: только 3 фазы (взлёт/пик/приземление), нет подхода/выезда, нет confidence scoring
- Отсутствует мотивационный слой — нет прогрессии, навыков, долгосрочной обратной связи
- skating-AI-analyzer проверил на практике: 5 суб-оценок, геймификация, confidence-based fallback — работают для детей FS1

## Scope

### Включает
1. **Многомерный скоринг** — 5 суб-оценок с весами, data quality flags
2. **Улучшение фазового определения** — 5 фаз, confidence scoring, TAS интеграция
3. **MVP-геймификация** — 5 уровней, 9 навыков (3 категории × 3 tiers), XP, тренировочные планы
4. **API и БД** — новые таблицы и endpoints
5. **Фронтенд** — визуализация суб-оценок, прогресса, таймлайна фаз

### НЕ включает
- LLM-vision в продакшене (только для разработки/валидации)
- IceBuddy / AI-тренер с долгосрочной памятью (out of scope)
- Полноценное дерево навыков ISU FS1-FS10 (MVP: 9 навыков)
- Персонажи и аватары
- Мобильное приложение
- Платёжная интеграция

## Архитектура

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Phase Detection │ ──→ │ Multi-Score     │ ──→ │ Gamification   │
│  (5 фаз + conf)  │     │ (5 subscores)   │     │ (XP + Skills)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                        │                        │
        └────────────────────────┴────────────────────────┘
                                 ↓
                    ┌─────────────────────┐
                    │  Russian Report     │
                    │  (Recommender +     │
                    │   Training Plan)    │
                    └─────────────────────┘
```

## 1. Многомерный скоринг

### Текущее состояние
`ml/src/analysis/metrics.py:1292` — `compute_goe_score()` даёт один proxy 0-10 с 6 компонентами.

### Новая модель

| Суб-оценка | Метрики | Вес в overall |
|---|---|---|
| **Взлётная мощь** (`takeoff_power`) | airtime, relative_jump_height, approach_consistency | 30% |
| **Ось вращения** (`rotation_axis`) | rotation_speed, total_rotation_deg, under_rotation_deg | 25% |
| **Координация рук** (`arm_coordination`) | arm_position_score, symmetry | 15% |
| **Амортизация приземления** (`landing_absorption`) | landing_knee_angle, landing_knee_stability, landing_smoothness, hard_landing | 25% |
| **Стабильность корпуса** (`core_stability`) | landing_trunk_recovery, approach_torso_lean, trunk_lean | 10% |

**Score floor:**
- Применяется только к `overall` (не к отдельным subscores):
  - `data_quality=good` + нет high-severity issues → minimum overall ≥ 4.0
  - `data_quality=partial` → minimum overall ≥ 3.0
- Disabled при `skeleton_reliability=likely_wrong`
- Subscores остаются без floor (отражают реальные метрики)

### Сущности

```python
# ml/src/analysis/types.py
@dataclass
class SubScore:
    name: str
    label_ru: str
    value: float       # 0-10
    confidence: float  # 0-1
    contributing_metrics: list[str]

@dataclass
class MultiDimensionalScore:
    subscores: list[SubScore]
    overall: float
    data_quality: str      # good / partial / poor
    skeleton_reliability: str  # reliable / uncertain / likely_wrong
```

### Бэкенд
- Новая таблица `session_scores` (JSONB с subscores)
- Endpoint `GET /sessions/{id}/scores`
- Миграция Alembic

### Фронтенд
- Компонент `<ScoreBreakdown>` — столбчатая или радар-диаграмма
- Цветовая кодировка: зелёный ≥7, жёлтый 5-7, красный <5

## 2. Улучшение фазового определения

### Текущее состояние
CoM-based: 3 фазы (взлёт/пик/приземление). Нет confidence, нет TAS интеграции.

### Новые фазы

| Фаза | Определение |
|---|---|
| **Подход** (`approach`) | CoM ускорение > порога + ноги на льду |
| **Взлёт** (`takeoff`) | Последний кадр с ногами на льду → первый в воздухе |
| **Полёт** (`air`) | CoM между takeoff и landing (существующее) |
| **Приземление** (`landing`) | CoM минимум после пика + скорость вниз |
| **Выезд** (`glide_out`) | CoM горизонтальная скорость стабилизировалась |

### Confidence scoring
| Фактор | Вклад |
|---|---|
| Параболическая R² ≥ 0.9 | +0.3 |
| Tracking confidence ≥ 0.7 | +0.3 |
| Gap ratio ≥ 0.8 | +0.2 |
| Порядок T < P < L валиден | +0.2 |

### TAS интеграция
- `TASElementSegmenter` (`ml/src/tas/inference.py`) даёт coarse labels (None/Jump/Spin/Step)
- CoM уточняет границы внутри TAS-сегмента
- TAS fine classifier определяет element_type (Waltz, Axel и т.д.)
- Fallback: TAS недоступен → CoM-only (3 фазы), element_type=null

### Сущности

```python
# ml/src/analysis/types.py
@dataclass
class Phase:
    name: str
    start_frame: int
    end_frame: int
    start_time: float
    end_time: float
    confidence: float
    detection_method: str  # com_parabola | tas_segment | heuristic

@dataclass
class PhaseDetectionResult:
    phases: list[Phase]
    overall_confidence: float
    element_type: str | None
    fallback_used: bool
```

### Бэкенд
- Таблица `session_phases` (JSONB)
- Endpoint `GET /sessions/{id}/phases`

### Фронтенд
- Таймлайн видео с цветными маркерами фаз
- Hover → confidence tooltip
- Warning при confidence < 0.5

## 3. Геймификация (MVP)

### Уровни

| Уровень | XP | Название |
|---------|-----|----------|
| 1 | 0 | Новичок |
| 2 | 100 | Юниор |
| 3 | 300 | Спортсмен |
| 4 | 700 | Мастер |
| 5 | 1500 | Чемпион |

### Навыки (9 штук)

| Категория | Бронза (50 XP) | Серебро (150 XP) | Золото (300 XP) |
|-----------|---------------|------------------|-----------------|
| **Взлёты** | 1 прыжок ≥5.0 | 3 прыжка ≥6.0 | 5 прыжков ≥7.0 |
| **Вращения** | 1 вращение ≥5.0 | 2 вращения ≥6.0 | 3 вращения ≥7.0 |
| **Контроль** | symmetry ≥0.6 | symmetry ≥0.7 | symmetry ≥0.8 |

### Правила
- Разблокировка: `consecutive_sessions` с нужным score
- XP = `overall * 10` за сессию (scale 0-10 → 0-100) + бонус за навык (bronze=50, silver=150, gold=300)
- После 14 дней без тренировки — XP не начисляется, не убывает

### Тренировочный план
- Генерируется после анализа на основе weakest subscore
- Формат: 3-5 пунктов с приоритетом
- Перегенерация при новом анализе, старый — `superseded`

### Сущности

```python
# backend/app/models/
class UserLevel(Base):
    user_id: UUID
    level: int  # 1-5
    total_xp: int
    xp_to_next: int

class SkillProgress(Base):
    user_id: UUID
    skill_id: str
    category: str  # jumps / spins / control
    tier: str      # bronze / silver / gold
    unlocked: bool
    unlocked_at: datetime
    consecutive_sessions: int
    best_score: float

class TrainingPlan(Base):
    user_id: UUID
    session_id: UUID
    plan_items: JSONB
    generated_at: datetime
    completed: bool
```

### Бэкенд
- Endpoints: `GET /users/{id}/level`, `GET /users/{id}/skills`, `POST /training-plans/generate`
- XP начисление — триггер после завершения анализа
- Skill unlock — background check после сохранения scores

### Фронтенд
- `<GamificationPanel>` — уровень, XP bar, сетка навыков 3×3
- `<TrainingPlan>` — чекбоксы для пунктов
- В профиле пользователя

## 4. Таблицы БД

```sql
-- session_phases
CREATE TABLE session_phases (
    session_id UUID PRIMARY KEY REFERENCES sessions(id),
    phases JSONB NOT NULL,
    overall_confidence FLOAT,
    element_type VARCHAR,
    fallback_used BOOLEAN DEFAULT FALSE
);

-- session_scores
CREATE TABLE session_scores (
    session_id UUID PRIMARY KEY REFERENCES sessions(id),
    subscores JSONB NOT NULL,
    overall FLOAT,
    data_quality VARCHAR,
    skeleton_reliability VARCHAR,
    computed_at TIMESTAMP
);

-- user_levels
CREATE TABLE user_levels (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    level INT NOT NULL DEFAULT 1,
    total_xp INT NOT NULL DEFAULT 0,
    xp_to_next INT NOT NULL DEFAULT 100
);

-- skill_progress
CREATE TABLE skill_progress (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    skill_id VARCHAR NOT NULL,
    category VARCHAR NOT NULL,
    tier VARCHAR NOT NULL,
    unlocked BOOLEAN DEFAULT FALSE,
    unlocked_at TIMESTAMP,
    consecutive_sessions INT DEFAULT 0,
    best_score FLOAT,
    UNIQUE(user_id, skill_id)
);

-- training_plans
CREATE TABLE training_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    session_id UUID REFERENCES sessions(id),
    plan_items JSONB NOT NULL,
    generated_at TIMESTAMP DEFAULT NOW(),
    completed BOOLEAN DEFAULT FALSE
);
```

## 5. Worker Pipeline

Новый порядок:
```
detect → pose → tracking → phase_detection (5 phases + TAS) → metrics
  → multi_score (5 subscores) → gamification (XP + skill check)
  → recommender → training_plan → report
```

## 6. Error Handling и Edge Cases

| Сценарий | Поведение |
|----------|-----------|
| `overall_confidence < 0.5` | fallback_used=true, data_quality="poor" |
| `gap_ratio > 0.4` | skeleton_reliability="likely_wrong", score floor 3.0 |
| TAS не определил element_type | element_type=null, generic recommender rules |
| Tracking switched target | Worker завершает с ошибкой `tracking_lost`; пользователь уведомляется через SSE |
| TAS ONNX не загружен | CoM-only, 3 фазы |
| CoM R² < 0.5 | Heuristic thresholds |
| Multi-score недоступен | Возвращаем существующий GOE proxy |

## 7. API Endpoints

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/sessions/{id}/phases` | GET | Фазы с confidence |
| `/sessions/{id}/scores` | GET | Суб-оценки + overall |
| `/users/{id}/level` | GET | Уровень + XP |
| `/users/{id}/skills` | GET | Прогресс навыков |
| `/training-plans/generate` | POST | Сгенерировать план |
| `/training-plans/{id}` | GET | Получить план |

## 8. Файлы для изменения

### ML
- `ml/src/analysis/metrics.py` — добавить `compute_subscores()`, `compute_data_quality_flags()`
- `ml/src/analysis/phase_detection.py` — расширить до 5 фаз, добавить approach/glide_out
- `ml/src/analysis/types.py` — `SubScore`, `MultiDimensionalScore`, `Phase`, `PhaseDetectionResult`
- `ml/src/tas/inference.py` — интегрировать в основной пайплайн
- Новый: `ml/src/analysis/confidence.py` — confidence scoring
- Новый: `ml/src/analysis/multi_score.py` — сборка суб-оценок
- Новый: `ml/src/analysis/training_plan.py` — генерация плана

### Бэкенд
- `backend/app/models/` — новые модели UserLevel, SkillProgress, TrainingPlan
- `backend/app/schemas.py` — новые Pydantic schemas
- `backend/app/routes/` — новые роутеры (scores, phases, gamification, training_plans)
- `backend/app/crud/` — CRUD для новых таблиц
- `backend/app/worker.py` — обновить порядок пайплайна
- Alembic миграции

### Фронтенд
- `frontend/components/ScoreBreakdown.tsx` — визуализация суб-оценок
- `frontend/components/GamificationPanel.tsx` — уровни и навыки
- `frontend/components/TrainingPlan.tsx` — план тренировок
- `frontend/components/PhaseTimeline.tsx` — таймлайн фаз на видео
- `frontend/lib/api.ts` — новые API клиенты

## 9. Тестирование

- Каждая суб-оценка — unit test с известными входными метриками и ожидаемым выходом
- Phase detection — тест на синтетических CoM-кривых (парабола + noise)
- Confidence scoring — тест на комбинации факторов
- Gamification — тест на последовательное начисление XP и разблокировку
- Integration — полный пайплайн на тестовом видео

## 10. Метрики успеха

- Все 5 суб-оценок вычисляются корректно (валидация на тестовых данных)
- Фазы определяются с overall_confidence ≥ 0.7 на 80%+ сессий
- Геймификация: пользователь видит прогресс после первой сессии
- Тренировочный план генерируется ≤500ms
- Нет регрессии в существующем GOE proxy score (fallback работает)
