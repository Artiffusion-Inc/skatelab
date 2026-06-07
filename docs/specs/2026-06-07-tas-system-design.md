# SkateLab — Temporal Action Segmentation (TAS) System Design

## Цель
Построить систему temporal action segmentation для фигурного катания с тремя уровнями: coarse TAS (границы элементов), phase detection (фазы внутри элемента), fine classification (тип элемента). Используем только то, что уже есть в кодовой базе или может быть быстро реализовано.

## Scope

### Включает
1. **Coarse TAS** — BiGRUTASRefiner (код готов) на MCFS, 4 класса (None/Jump/Spin/Step)
2. **Phase Detection** — расширить CoM-геометрию с 3 до 5 фаз + confidence
3. **Fine Classification v1** — BiGRU clip-level classifier на SkatingVerse (код готов в `extract_skatingverse_quick.py`)
4. **Интеграция** — 3 уровня в единый пайплайн

### НЕ включает
- MS-GCN, MS-TCN++ — не реализованы, нет ресурсов
- InfoGCN — не реализован, сложная GCN-архитектура
- UniformerV2 — video-based, требует RGB, тяжёлый
- MeTRAbs — pose estimation, не classification
- SkatingVerse скачивание — отдельная задача

---

## Архитектура

```
Видео целиком
  → YOLOv8n + MogaNet-B ONNX (существующий пайплайн)
    → H3.6M poses (T, 17, 2)
      → [Уровень 1] Coarse TAS: BiGRUTASRefiner → segments [Jump/Spin/Step]
        → [Уровень 2] Phase Detection: CoM-геометрия → фазы внутри элемента
          → [Уровень 3] Fine Classification: BiGRU clip-level → тип элемента
            → Multi-Score → Gamification → Report
```

---

## Уровень 1: Coarse TAS

### Что используем
**BiGRUTASRefiner** — код готов в `ml/src/tas/model.py`, `ml/src/tas/inference.py`.

| Параметр | Значение |
|----------|----------|
| Архитектура | BiGRU (34→128→4) + BoundaryRefinerCNN |
| Input | (T, 17, 2) H3.6M poses |
| Output | Frame-wise: None/Jump/Spin/Step |
| ONNX | Экспорт через `experiments/train_tas_v2.py` |
| Статус | **Код готов, нужен training** |

### Датасет
**MCFS** — 271 видео, 1.7M frame labels, 130 fine → 4 coarse.

**Проблемы и решения:**
- 56% frames с missing joints → GapFiller (уже есть)
- Labels сдвинуты ~57 кадров → shift correction
- Нужно: запустить `experiments/train_tas.py` или `experiments/train_tas_v2.py`

### Метрика
**OverlapF1@50** — уже реализован в `ml/src/tas/metrics.py`.

### Fallback
- Если модель не загружена / не натренирована → rule-based (motion energy thresholds)
- Если confidence < 0.5 → эвристики

---

## Уровень 2: Phase Detection

### Что используем
Существующая CoM-геометрия + расширение.

**Текущее:** 3 фазы (взлёт/пик/приземление) через параболическую аппроксимацию.

**Новое:** 5 фаз для прыжков:

| Фаза | Определение |
|------|-------------|
| Подход | CoM ускорение > порога |
| Взлёт | Последний кадр с ногами на льду |
| Полёт | Между взлётом и приземлением (существующее) |
| Приземление | Первый кадр с ногами на льду после полёта |
| Выезд | CoM горизонтальная скорость стабилизировалась |

### Confidence scoring
| Фактор | Вклад |
|---|---|
| Параболическая R² ≥ 0.9 | +0.3 |
| Tracking confidence ≥ 0.7 | +0.3 |
| Gap ratio ≥ 0.8 | +0.2 |
| Порядок фаз валиден | +0.2 |

---

## Уровень 3: Fine Classification v1

### Что используем
**BiGRU clip-level classifier** — код уже написан в `experiments/extract_skatingverse_quick.py`.

| Параметр | Значение |
|----------|----------|
| Архитектура | BiGRU (34→128→N_classes) |
| Input | Clip poses (T, 17, 2) |
| Output | Класс элемента (Axel/Salchow/Loop/etc.) |
| Код | `experiments/extract_skatingverse_quick.py:199-218` |
| Статус | **Код готов, нужен training на SkatingVerse** |

### Датасет
**SkatingVerse** — 28 классов, но **видео не скачаны**.

**Блокер:** Нужно сначала скачать видео с `gdrive-advanced:/SkatingVerse`.

**Без SkatingVerse:** Fine classification v1 — **не может быть обучен**. Будет заглушка (rule-based или пропуск).

### Fallback
- Если fine classifier не обучен → element_type = null, generic metrics
- Если confidence < 0.6 → "unknown_element"

---

## Модели и Checkpoints (реалистичный статус)

| Модель | Статус | Путь | Что нужно |
|--------|--------|------|-----------|
| **BiGRUTAS** | Код готов | `ml/src/tas/model.py` | **Training на MCFS** |
| **BiGRUTASRefiner** | Код готов | `ml/src/tas/model.py` | **Training на MCFS** |
| **TASElementSegmenter** | ONNX inference готов | `ml/src/tas/inference.py` | Только checkpoint |
| **RF Classifier** | Код готов | `ml/src/tas/classifier.py` | **Training на MCFS segments** |
| **BiGRU clip-classifier** | Код готов | `experiments/extract_skatingverse_quick.py` | **SkatingVerse + training** |

### Что НЕ используем (и почему)

| Модель | Почему нет |
|--------|-----------|
| MS-GCN | Не реализован, нет кода |
| MS-TCN++ | Не реализован, нет кода |
| InfoGCN | Не реализован, сложная GCN-архитектура, требует torch-geometric |
| UniformerV2 | Video-based, требует RGB, тяжёлый |
| MeTRAbs | Pose estimation, не classification |
| rtmlib | Не в production dependencies |

---

## Пайплайн обучения

### Шаг 1: Coarse TAS (MCFS, приоритет #1)
```
MCFS данные (271 видео)
  → Gap filling + smoothing
    → Label shift correction (-57 frames)
      → BiGRUTASRefiner training
        → ONNX export
          → TASElementSegmenter (production)
```

**Команды:**
```bash
# Training
uv run python experiments/train_tas_v2.py

# ONNX export
uv run python experiments/export_tas_onnx.py --checkpoint <path>
```

### Шаг 2: Fine Classification (SkatingVerse, приоритет #2)
```
SkatingVerse MP4 (нужно скачать)
  → YOLOv8n + MogaNet-B ONNX (существующий пайплайн)
    → H3.6M poses
      → BiGRU clip-classifier training
        → ONNX export
```

**Блокер:** Скачивание SkatingVerse видео.

**Без SkatingVerse:** Шаг 2 пропускаем, fine classification v1 = заглушка.

---

## Интеграция в Worker Pipeline

```
detect → pose → tracking
  → Coarse TAS (BiGRUTASRefiner ONNX)
    → Для каждого сегмента:
      → Phase Detection (CoM, 5 фаз)
      → Fine Classification (BiGRU ONNX, если обучен)
    → Metrics (на фазах)
    → Multi-Score (5 subscores)
    → Gamification
    → Report
```

**Async/parallel внутри worker:**
- Coarse TAS + Phase Detection можно запускать последовательно (TAS даёт границы, Phase работает внутри)
- Fine Classification для каждого сегмента — параллельно (независимые клипы)
- Metrics + Multi-Score — после всех фаз

---

## API Endpoints

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/sessions/{id}/elements` | GET | Список элементов с границами |
| `/sessions/{id}/elements/{id}/phases` | GET | Фазы элемента |
| `/sessions/{id}/elements/{id}/type` | GET | Fine classification (или null) |

---

## Error Handling и Fallbacks

| Сценарий | Fallback |
|----------|----------|
| BiGRUTASRefiner не загружен | Rule-based (motion energy thresholds) |
| Coarse TAS confidence < 0.5 | Эвристики |
| Fine classifier не обучен | element_type = null |
| Fine classifier confidence < 0.6 | "unknown_element" |
| Phase detection failed | 3 базовые фазы (взлёт/полёт/приземление) |

---

## Метрики успеха

| Метрика | Цель |
|---------|------|
| Coarse TAS F1@50 (MCFS) | > 0.70 (реалистично для BiGRU) |
| Phase detection confidence | ≥ 0.7 на 80%+ прыжков |
| Fine Classification accuracy | > 80% на SkatingVerse (если обучен) |
| Inference speed (coarse TAS) | ≤ 100ms на секунду видео |
| Inference speed (fine clf) | ≤ 50ms на клип |

---

## Ресурсы

### GPU
- BiGRUTASRefiner training: 1× GPU, ~8ч
- BiGRU clip-classifier training: 1× GPU, ~12ч (если SkatingVerse готов)

### Библиотеки
- `torch` (training only)
- `onnxruntime-gpu` (inference)
- `scikit-learn` (RF classifier)
- Уже в `ml/pyproject.toml`

---

## Что делать сейчас (приоритеты)

1. **Запустить BiGRUTASRefiner training** на MCFS — `experiments/train_tas_v2.py`
2. **Проверить ONNX export** — `experiments/export_tas_onnx.py`
3. **Расширить Phase Detection** до 5 фаз — `ml/src/analysis/phase_detection.py`
4. **Скачать SkatingVerse** — `rclone copy gdrive-advanced:/SkatingVerse` (отдельная задача)
5. **Обучить BiGRU clip-classifier** — после SkatingVerse готов

---

## Что НЕ делать

- Не писать MS-GCN / MS-TCN++ / InfoGCN с нуля
- Не добавлять rtmlib в dependencies
- Не ждать SkatingVerse для ship'а MVP (coarse TAS + phases работают без fine classifier)
