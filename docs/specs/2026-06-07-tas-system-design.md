# SkateLab — Temporal Action Segmentation (TAS) System Design

## Цель
Построить полную систему temporal action segmentation для фигурного катания с тремя уровнями: coarse TAS (границы элементов), phase detection (фазы внутри элемента), fine classification (тип элемента). Приоритет: fine classification на SkatingVerse.

## Мотивация
- Сейчас SkateLab определяет только прыжки по CoM-параболе, не знает тип прыжка (Axel vs Salchow)
- Нет различения вращений (Camel vs Sit vs Layback)
- Нет обнаружения дорожек шагов и хореографии
- skating-AI-analyzer использует Qwen vision для определения типа — дорого, не масштабируется
- SkatingVerse датасет (28K клипов) уже скачан на сервере и готов к использованию

## Архитектура трёх уровней

```
┌─────────────────────────────────────────────────────────────┐
│                    Вход: Видео целиком                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Уровень 1: Coarse TAS (frame-wise)                        │
│  MS-GCN / MS-TCN++ на скелетах H3.6M                       │
│  Выход: None / Jump / Spin / Step / Choreo                │
│  Границы: start_frame, end_frame для каждого элемента     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Уровень 2: Phase Detection (внутри элемента)              │
│  CoM-геометрия + кинематические ограничения               │
│  Выход: Заход / Взлёт / Полёт / Приземление / Выезд       │
│  (для прыжков); Вход / Основная / Выход (для вращений)    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Уровень 3: Fine Classification (clip-level)               │
│  InfoGCN / UniformerV2 на скелетах                         │
│  Выход: Axel_2T / Salchow_3T / CamelSpin_3 / ...          │
│  28 классов SkatingVerse → расширение до ~50 ISU типов    │
└─────────────────────────────────────────────────────────────┘
```

---

## Уровень 3: Fine Classification (Приоритет #1)

### Задача
По видео-клипу (уже вырезанному элементу) определить:
- Тип прыжка (6 семейств) + количество оборотов
- Тип вращения + уровень
- Тип дорожки (StepSeq / ChoreoSeq / ...)

### Датасеты

#### SkatingVerse (основной)
| Параметр | Значение |
|----------|----------|
| Клипов | 28K (19,993 train + 8,586 test) |
| Часов | ~184 |
| Классов | 28 (23 прыжка + 3 вращения + 2 junk) |
| Формат | MP4, TV broadcast |
| **Статус** | **Не скачан полностью** — на сервере только метаданные (mapping.txt, train.txt, answer.txt, 677KB) |
| **Где взять** | Нужно скачать через rclone с gdrive-advanced:/SkatingVerse/train_videos/ и test_videos/ |
| Labels | train.txt: `filename label_id` |
| Проблема | Нужно скачать видео + извлечь скелеты — ~40ч GPU |

**Действия:**
1. `rclone copy gdrive-advanced:/SkatingVerse data/SkatingVerse/` — скачать полный датасет
2. `python data/data_tools/convert_skatingverse.py` — извлечь скелеты (MogaNet-B + normalization)
3. Или `python experiments/extract_skatingverse_quick.py --step extract` — quick extraction

**Классы SkatingVerse (28):**
```
# Прыжки (23 = 6 семейств × обороты, minus некоторые)
Axel_1T, Axel_2T, Axel_3T
Flip_1T, Flip_2T, Flip_3T, Flip_4T
Lutz_1T, Lutz_2T, Lutz_3T, Lutz_4T
Loop_1T, Loop_2T, Loop_3T, Loop_4T
Salchow_1T, Salchow_2T, Salchow_3T, Salchow_4T
Toeloop_1T, Toeloop_2T, Toeloop_3T, Toeloop_4T

# Вращения (3)
CamelSpin, SitSpin, UprightSpin

# Junk (2, skip)
No_Basic (class 12), Sequence (class 27)
```

**Расширение до ISU taxonomy:**
Добавить: Euler, ComboSpin variations, LaybackSpin, Biellmann, ChoreoStep, Spiral, SpreadEagle, Stroking, mohawk, choctaw, etc.
→ ~50 классов.

#### AthletePose3D (для pose pre-training)
| Параметр | Значение |
|----------|----------|
| Размер | 37GB (pose_2d.zip 31GB + pose_3d.zip 1.5GB) |
| Камер | 4, калиброванные |
| Формат | H3.6M 17kp, GT 3D |
| Назначение | Pre-training pose estimator, не для TAS |

#### MCFS (для coarse TAS training)
| Параметр | Значение |
|----------|----------|
| Видео | 271 |
| Frame labels | 1.7M |
| Classes | 130 fine |
| Проблема | 56% missing joints, ±57 кадров ошибки |

#### FineFS (дополнительный)
| Параметр | Значение |
|----------|----------|
| Видео | 1167 (по данным из исследования) |
| Labels | Routine-level (не frame-level) |

### Модели

#### InfoGCN (Primary — skeleton-based)
| Параметр | Значение |
|----------|----------|
| Архитектура | GCN с информационными потоками между суставами |
| Input | Скелет COCO 17kp / H3.6M 17kp, T frames |
| Преимущества | Работает только со скелетами (не нужен RGB) |
| Результат DeepGlint | 92.03% на SkatingVerse |
| Зависимости | torch, torch-geometric или custom GCN |

#### UniformerV2 (Secondary — video-based)
| Параметр | Значение |
|----------|----------|
| Архитектура | Video Vision Transformer |
| Input | Raw video frames |
| Преимущества | SOTA accuracy (95.02% у DeepGlint) |
| Недостатки | Тяжёлый, требует RGB, дороже inference |
| Использование | Teacher model для distillation на InfoGCN |

#### MeTRAbs (DS_Skating — для сравнения)
| Параметр | Значение |
|----------|----------|
| Назначение | 3D pose estimation, не classification |
| Модели | MobileNet-based (`metrabs_mob3l_y4t`) / EfficientNet-based |
| Источник | RWTH Aachen (omnomnom.vision.rwth-aachen.de) |
| Применимость | Извлечь скелеты из SkatingVerse клипов |

### Пайплайн обучения (Fine Classification)

```
SkatingVerse MP4 клипы
  → Extract poses (SkateLab pipeline: YOLOv8n + MogaNet-B ONNX)
    → COCO 17kp → H3.6M 17kp (наша конверсия)
      → Normalization (root-center + spine-scale)
        → InfoGCN training
          → [SkatingVerse 28 classes]
            → Fine-tune на ISU taxonomy (~50 classes)
              → MCFS / TAS-AnnoTools annotated clips
                → Final model
```

**Шаг 1: Pose Extraction (~40ч GPU)**
- Используем существующий SkateLab pipeline: YOLOv8n + MogaNet-B (ONNX, 384×288)
- Каждый клип SkatingVerse → `.npz` с poses (T, 17, 2) в H3.6M формате
- Параллельно на Vast.ai GPU
- Альтернатива для сравнения: MeTRAbs (DS_Skating repo)

**Шаг 2: Training InfoGCN**
- 80/20 split на SkatingVerse train
- 5-fold CV
- Adam, lr=1e-3, cosine annealing
- Data augmentation: random rotation, scaling, temporal jitter
- Target: >90% accuracy (beat DeepGlint's single model 92%)

**Шаг 3: Expansion to ISU**
- Добавить классы: Euler, Combo spins, Step variations
- Pseudo-labeling через уверенные предсказания
- Manual annotation через TAS-AnnoTools для редких классов

### Сущности

```python
# ml/src/tas/fine_classifier.py
@dataclass
class FineClassificationResult:
    element_type: str        # "axel", "salchow", "camel_spin", ...
    rotation_count: int | None # 1, 2, 3, 4 (для прыжков)
    spin_level: str | None     # "B", "1", "2", "3", "4" (для вращений)
    confidence: float        # 0-1
    model_used: str          # "infogcn" | "uniformerv2" | "ensemble"

class FineElementClassifier:
    def __init__(self, model_path: str, device: str = "cuda"):
        self.model = load_infogcn(model_path)

    def classify(self, poses: np.ndarray, fps: float = 30.0) -> FineClassificationResult:
        # poses: (T, 17, 2) or (T, 17, 3)
        # Returns element type + confidence
        pass
```

---

## Уровень 1: Coarse TAS (Frame-wise Segmentation)

### Задача
По полному видео (программа целиком) определить:
- Где начинается и заканчивается каждый элемент
- Frame-wise label: None / Jump / Spin / Step / Choreo

### Модели

#### MS-GCN (Primary)
| Параметр | Значение |
|----------|----------|
| Архитектура | Multi-Stage Graph Convolutional Network |
| Input | Скелет H3.6M 17kp, T frames |
| Преимущества | Специализирован для скелетов, захватывает пространственно-временные связи |
| Сравнение | MS-TCN++ — лучше на general datasets, но GCN лучше для скелетов |

#### MS-TCN++ (Fallback)
| Параметр | Значение |
|----------|----------|
| Архитектура | Multi-Stage Temporal Convolutional Network |
| Input | Скелет или feature sequence |
| Преимущества | SOTA на Breakfast, 50Salads, GTEA |
| Недостатки | Не учитывает графовую структуру скелета |

#### BiGRUTAS (уже есть в коде)
| Параметр | Значение |
|----------|----------|
| Статус | Код готов, **не натренирован** |
| Результат (ожидаемый) | F1@50 ~0.7-0.8 на MCFS |
| Решение | Использовать как baseline, заменить на MS-GCN если F1 < 0.75 |

### Датасет
**MCFS** — 271 видео, 1.7M frame-level labels, 130 fine → 4 coarse classes.

**Проблемы MCFS:**
- 56% frames с missing joints (OpenPose BODY_25)
- Labels сдвинуты ~57 кадров (ошибка аннотации)
- Нужно: заполнить gaps (`ml/src/utils/gap_filler.py`), применить temporal smoothing

**Решение проблем:**
1. Gap filling — 3-tier interpolation
2. One-Euro smoothing
3. Label shift correction — сдвинуть все labels на -57 frames (эмпирически)
4. Pseudo-label на SkatingVerse (train на MCFS, pseudo-label на SkatingVerse полные программы)

### Метрика
**OverlapF1@50** — IoU ≥ 0.5 для matching segment.

```python
# ml/src/tas/metrics.py (уже есть)
def overlap_f1(pred_segments, gt_segments, iou_threshold=0.5):
    # pred_segments: [{label, start, end}, ...]
    # gt_segments: [{label, start, end}, ...]
    # Returns: F1 score
```

### Сущности

```python
# ml/src/tas/coarse_segmenter.py
@dataclass
class CoarseSegment:
    label: str       # "jump", "spin", "step", "choreo"
    start_frame: int
    end_frame: int
    start_time: float
    end_time: float
    confidence: float

class CoarseTASSegmenter:
    def __init__(self, model_path: str):
        self.model = load_ms_gcn(model_path)  # или BiGRUTAS

    def segment(self, poses: np.ndarray, fps: float = 30.0) -> list[CoarseSegment]:
        # poses: (T, 17, 2) или (T, 17, 3)
        # Returns list of segments
        pass
```

---

## Уровень 2: Phase Detection

### Задача
Внутри каждого элемента (полученного от Coarse TAS) определить фазы:

**Для прыжков:**
| Фаза | Определение | Метод |
|------|-------------|-------|
| Заход (`approach`) | Движение к точке взлёта | CoM ускорение + ноги на льду |
| Взлёт (`takeoff`) | Отрыв от льда | CoM пересечение threshold + скорость вверх |
| Полёт (`air`) | В воздухе | CoM между takeoff и landing |
| Приземление (`landing`) | Касание льда | CoM минимум + скорость вниз |
| Выезд (`glide_out`) | Стабилизация | CoM горизонтальная скорость стабильна |

**Для вращений:**
| Фаза | Определение |
|------|-------------|
| Вход (`entry`) | Подготовка к вращению |
| Основная (`main`) | Вращение на одной ноге |
| Выход (`exit`) | Смена позиции / остановка |

**Для дорожек:**
- Хореографическая vs техническая — через fine classifier (UniformerV2 может различить по стилю движения)

### Confidence Scoring
| Фактор | Вклад |
|---|---|
| Параболическая R² ≥ 0.9 | +0.3 |
| Tracking confidence ≥ 0.7 | +0.3 |
| Gap ratio ≥ 0.8 | +0.2 |
| Порядок фаз валиден | +0.2 |

### Сущности

```python
# ml/src/analysis/phase_detection.py (расширить)
@dataclass
class Phase:
    name: str
    start_frame: int
    end_frame: int
    start_time: float
    end_time: float
    confidence: float
    detection_method: str  # com_parabola | heuristic

@dataclass
class PhaseDetectionResult:
    phases: list[Phase]
    overall_confidence: float
    element_type: str | None
    fallback_used: bool
```

---

## Интеграция трёх уровней

### Полный пайплайн (production)

```
Вход: полное видео программы
  → Person detection (YOLOv8n) + MogaNet-B pose estimation
    → Tracking (DeepSORT) + TrackValidator
      → Coarse TAS (MS-GCN) — Уровень 1
        → [Jump segment] → Phase Detection (CoM) — Уровень 2
          → [Clip] → Fine Classification (InfoGCN) — Уровень 3
            → Element: "Axel_3T", phases: [approach, takeoff, air, landing, glide_out]
        → [Spin segment] → Phase Detection (rotation-based)
          → [Clip] → Fine Classification (InfoGCN)
            → Element: "CamelSpin_3", phases: [entry, main, exit]
        → [Step segment]
          → [Clip] → Fine Classification (InfoGCN)
            → Element: "StepSequence" or "ChoreoSequence"
```

### Worker Pipeline (обновлённый)

```
detect → pose → tracking → Coarse TAS (Уровень 1)
  → Для каждого сегмента:
    → Phase Detection (Уровень 2)
    → Fine Classification (Уровень 3)
  → Metrics (на фазах)
  → Multi-Score (5 subscores)
  → Gamification
  → Report
```

---

## Датасеты на сервере

### Что уже есть
| Датасет | Локация | Размер | Тип labels |
|---------|---------|--------|-----------|
| AthletePose3D | `data/AthletePose3D/` | 37GB | GT 3D poses, 4 cameras |
| MCFS-130 | `data/MCFS-130/` | 108MB | Frame-level, 130 classes |
| FSAnno | `data/FSAnno/` | 15KB | annotations/ (структура неизвестна) |
| FineFS | `data/FineFS/` | ? | data/ (структура неизвестна) |
| SkatingVerse | `data/SkatingVerse/` | 677KB (метаданные) | Clip-level, 28 classes |
| KD-teacher | `data/KD-teacher-outputs/` | 1.3GB | teacher coords + simcc |

### Что нужно сделать
1. **SkatingVerse** — скачать видео (train + test), извлечь скелеты
2. **MCFS** — почистить labels (shift correction, gap filling)
3. **FSAnno** — изучить структуру, возможно frame-level labels
4. **FineFS** — изучить структуру

### Pose Extraction Pipeline

**Production pipeline (MogaNet-B — основной):**
```
SkatingVerse MP4 / MCFS video
  → PersonDetector (YOLOv8n) — уже в пайплайне
    → MogaNet-B (ONNX, 384×288, COCO 17kp) — уже в пайплайне
      → coco_to_h36m() — уже в пайплайне
        → GapFiller (3-tier) — уже в пайплайне
          → Smoothing (One-Euro, Numba JIT) — уже в пайплайне
            → Output: (T, 17, 2) normalized H3.6M poses
```

**Для SkatingVerse pose extraction:**
Использовать существующий пайплайн `process_video_pipeline` с MogaNet-B, без rtmlib/RTMPose.

**Экспериментальные скрипты (не production-ready):**
- `experiments/extract_skatingverse_quick.py` — использует `rtmlib` (**не установлена**)
- `data/data_tools/convert_skatingverse.py` — использует `rtmlib` (**не установлена**)
- `ml/scripts/extract_skatingverse_frames.py` — frame extraction (OpenCV only, работает)
- `ml/scripts/pseudo_label_skatingverse.py` — MogaNet-B pseudo-labeling (работает)

**Note:** `experiments/rtmpose-simcc-kd/` содержит эксперименты по fine-tuning RTMPose-s с AthletePose3D, но rtmlib не в production dependencies. Для TAS используем существующий MogaNet-B pipeline.

---

## Модели и Checkpoints

### Текущее состояние
| Модель | Статус | Путь |
|--------|--------|------|
| BiGRUTAS | Код готов, **не натренирована** | `ml/src/tas/model.py` |
| BiGRUTASRefiner | Код гready, **не натренирована** | `ml/src/tas/model.py` |
| RF Classifier | Код готов, **не натренирован** | `ml/src/tas/classifier.py` |
| TASElementSegmenter | Готов (ONNX inference) | `ml/src/tas/inference.py` |
| MS-GCN | **Не реализован** | — |
| MS-TCN++ | **Не реализован** | — |
| InfoGCN | **Не реализован** | — |
| UniformerV2 | **Не реализован** | — |

### План обучения
1. **InfoGCN** — train на SkatingVerse (priority #1)
2. **MS-GCN** — train на MCFS (priority #2, если BiGRU F1 < 0.75)
3. **BiGRUTAS** — baseline на MCFS (уже есть код)

---

## TAS-AnnoTools (Manual Annotation)

### Когда использовать
- Создание ground-truth для редких классов (Euler, Biellmann, etc.)
- Валидация автоматических предсказаний
- Дообучение fine classifier

### Формат
- 56 элементов фигурного катания (21 категория)
- Frame-precise annotations (SQLite + JSON/CSV export)
- Web-based UI, keyboard shortcuts

### Интеграция
```
TAS-AnnoTools annotations
  → Export JSON
    → Convert to MCFS format
      → Merge with MCFS dataset
        → Retrain InfoGCN / MS-GCN
```

---

## API Endpoints

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/sessions/{id}/elements` | GET | Список элементов с границами (Coarse TAS) |
| `/sessions/{id}/elements/{id}/phases` | GET | Фазы элемента |
| `/sessions/{id}/elements/{id}/type` | GET | Fine classification результаты |
| `/elements/classify` | POST | Классифицировать клип (standalone) |

---

## Error Handling и Fallbacks

| Сценарий | Fallback |
|----------|----------|
| Coarse TAS confidence < 0.5 | Эвристики (motion energy thresholds) |
| Fine classifier confidence < 0.6 | "unknown_element", generic metrics |
| Phase detection failed | Return 3 базовые фазы (взлёт/полёт/приземление) |
| SkatingVerse model не загружен | Skip fine classification, использовать rule-based element detection |
| Tracking switched | `tracking_lost` error через SSE |

---

## Тестирование

### Unit Tests
- InfoGCN inference на синтетических скелетах
- Coarse TAS на MCFS (OverlapF1@50)
- Phase detection на синтетических CoM-кривых

### Integration Tests
- Полный pipeline на 5 тестовых видео из MCFS
- Сравнение: BiGRUTAS vs MS-GCN vs rule-based

### Validation
- Human evaluation: 100 случайных клипов, сравнение предсказаний vs ground truth
- Per-class accuracy для редких элементов

---

## Метрики успеха

| Метрика | Цель |
|---------|------|
| Fine Classification accuracy (SkatingVerse) | > 90% (beat single-model DeepGlint) |
| Coarse TAS F1@50 (MCFS) | > 0.75 |
| Phase detection confidence | ≥ 0.7 на 80%+ прыжков |
| Inference speed (fine classifier) | ≤ 50ms на клип |
| Inference speed (coarse TAS) | ≤ 100ms на секунду видео |
| Coverage (ISU элементы) | ≥ 30 типов распознаваемых |

---

## Ресурсы и Зависимости

### GPU
- Training InfoGCN: 1× V100 / A100, ~24ч
- Training MS-GCN: 1× V100, ~12ч
- Pose extraction SkatingVerse: 1× GPU, ~40ч

### Библиотеки
- `torch`, `torch-geometric` (InfoGCN, MS-GCN)
- `onnxruntime-gpu` (inference)
- `scikit-learn` (RF classifier)
- `ffmpeg-python` (video processing)

### Внешние ссылки
- DeepGlint paper: arXiv:2404.14032
- MeTRAbs: https://github.com/isarandi/metrabs
- MS-GCN: https://github.com/BenjaminFiltjens/MS-GCN
- MS-TCN++: https://github.com/sj-li/MS-TCN2
- TAS-AnnoTools: https://github.com/ryota-skating/TAS-AnnoTools
- mayupei: https://github.com/mayupei/figure-skating-action-segmentation
