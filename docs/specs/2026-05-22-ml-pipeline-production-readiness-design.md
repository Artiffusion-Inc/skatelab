# ML Pipeline Production Readiness — Design Spec

> Дата: 2026-05-22
> Статус: Final
> Scope: Full production readiness — bug fixes, quality audit, local GPU removal, PhysicsEngine integration
> Brainstorm report: `docs/specs/2026-05-22-ml-pipeline-brainstorm-report.md`

## Проблема

ML pipeline «работает» на уровне наличия кода, но содержит критические баги и не готов к продакшену:

1. **Axel rotations bug** — `int(1.5) = 1`, но axel = 1.5 оборота. Ломает `compute_under_rotation()`. Хак `+0.5` в 2 файлах.
2. **DTW hardcoded 33kp** — `motion_dtw.py` + `aligner.py` используют `list(range(33))` и `np.zeros((..., 33, 2))`, но формат H3.6M = 17 keypoints. 6+ мест.
3. **VizPipeline** — `build_layers()` добавляет только `VerticalAxisLayer`. Trail/Velocity/HUD не подключаются. Параллельный рендеринг слоёв невозможен (numpy race conditions).
4. **PhysicsEngine** — написан, но требует 3D `(N,17,3)`. Pipeline только 2D. Нужен 2D fallback. Stage 6.5 пустой.
5. **Local GPU path** — `detect_video_task` содержит fallback на local GPU. Мёртвый код. Vast.ai client без pooling/retry.
6. **Качество метрик** — airtime определяется CoM parabola. OOFSkate НЕ использует ice plane detection (подтверждено MIT). Улучшение <10%, не стоит инвестировать.

## Решения

### 1. Axel Rotations — `float` вместо `int`

**Проблема:** `ElementDef.rotations: int` — axel = `int(1.5) = 1`, что даёт target=360° вместо 540° для single axel. Хак `+0.5` в **2 местах** сломается при переходе на float.

**Решение:** Изменить тип `rotations` на `float`:

- `ElementDef.rotations: float` вместо `int`
- Axel: `rotations=1.5`, Double Axel: `rotations=2.5`, Triple Axel: `rotations=3.5`
- Single jumps: `rotations=1.0`
- Spins/steps: `rotations=0.0`
- `compute_under_rotation()` — убрать axel хак `+0.5` в `metrics.py` (строки 375-377), использовать `rotations` напрямую
- `jump_classifier.py` (строки 44-48) — убрать второй axel хак `+0.5`, использовать `rotations` напрямую
- `is_jump()` — `rotations > 0` работает с float
- Обновить все `ElementDef` в словаре `ELEMENT_DEFS`
- Обновить ideal ranges для double/triple axel (2.5, 3.5)

**Затронутые файлы:**
- `ml/src/analysis/element_defs.py` — тип, значения, `is_jump()`
- `ml/src/analysis/metrics.py` — `compute_under_rotation()`, убрать axel хак (строки 375-377)
- `ml/src/analysis/jump_classifier.py` — убрать axel хак (строки 44-48)

### 2. DTW — исправить hardcoded 33kp на runtime detection

**Проблема:** `motion_dtw.py` + `aligner.py` содержат `list(range(33))`, `np.zeros((..., 33, 2))` — пережиток BlazePose 33-keypoint формата. H3.6M = 17.

**Решение:** Заменить hardcoded 33 на runtime detection `poses.shape[1]`:

- `motion_dtw.py`: `joints=list(range(33))` → `joints=list(range(poses.shape[1]))` (строка 131)
- `motion_dtw.py`: `np.zeros((..., 33, 2))` → `np.zeros((..., poses.shape[1], 2))` (строки 388, 393)
- `aligner.py`: `joints=list(range(33))` → `joints=list(range(poses.shape[1]))` (строки 51, 91)
- `aligner.py`: `np.zeros((..., 33, 2))` → `np.zeros((..., poses.shape[1], 2))` (строка 223)
- Docstrings во всех файлах: `(num_frames, 33, 2)` → `(num_frames, num_joints, 2)`
- Padding fallback: `padding[:] = sequence[-1]` — работает для любого размера

**Затронутые файлы:**
- `ml/src/alignment/motion_dtw.py` — 3 места с `33` + docstrings
- `ml/src/alignment/aligner.py` — 3 места с `33` + docstrings
- `ml/src/analysis/element_segmenter.py` — docstrings (строки 92, 231, 237)
- `ml/src/analysis/phase_detector.py` — docstrings (строки 31, 81, 401)
- `ml/src/detection/pose_tracker.py` — docstrings (строки 195, 312)
- `ml/src/detection/spatial_reference.py` — docstrings (строка 223)

### 3. VizPipeline — Declarative Layer Registry

**Проблема:** `build_layers()` добавляет только `VerticalAxisLayer` при `layer >= 2`. Trail, Velocity, HUD, JointAngle — не подключаются. Параллельный рендеринг слоёв на одном фрейме невозможен (numpy race conditions, cv2 release GIL).

**Решение:** Declarative config с registry + level presets:

```python
LAYER_REGISTRY: dict[str, type[Layer]] = {
    "skeleton": SkeletonLayer,
    "trail": TrailLayer,
    "velocity": VelocityLayer,
    "joint_angle": JointAngleLayer,
    "vertical_axis": VerticalAxisLayer,
    "hud": HUDLayer,
    "blade": BladeLayer,
}

LEVEL_PRESETS: dict[int, list[str]] = {
    0: ["skeleton"],
    1: ["skeleton", "trail", "velocity"],
    2: ["skeleton", "trail", "velocity", "joint_angle", "vertical_axis"],
    3: ["skeleton", "trail", "velocity", "joint_angle", "vertical_axis", "hud", "blade"],
}

def build_layers(self) -> None:
    self.layers = []
    preset = LEVEL_PRESETS.get(self.layer, [])
    for name in preset:
        cls = LAYER_REGISTRY.get(name)
        if cls:
            self.layers.append(cls())
```

- Объединяет `VizPipeline.build_layers()` и `ComparisonRenderer._build_layers()` (string→class map)
- `add_ml_layers()` остаётся для ручного добавления
- Render — sequential per frame (industry standard: MMPose, AlphaPose, DeepLabCut)

**Затронутые файлы:**
- `ml/src/visualization/pipeline.py` — `build_layers()`, добавить registry + presets
- `ml/src/visualization/comparison.py` — унифицировать `_build_layers()` с registry

### 4. PhysicsEngine — 2D fallback + pipeline wiring

**Проблема:** `PhysicsEngine.analyze()` требует 3D `(N,17,3)`. Pipeline только 2D `(N,17,2)`. Stage 6.5 пустой — `physics_dict = {}`.

**Решение:** Добавить `analyze_2d()` fallback + wire в pipeline:

- `PhysicsEngine.analyze_2d(poses_2d, takeoff_idx, landing_idx, fps)` — 2D approximation
  - `calculate_com_trajectory(poses_2d)` — работает на `(N,17,2)` (уже есть в `geometry.py`)
  - jump_height из CoM parabola
  - flight_time из frame count / fps
  - takeoff_velocity из CoM derivative
  - `avg_inertia = None` (требует 3D)
  - fit_quality (R²) из parabola fit
- `PhysicsEngine.analyze(poses_3d, ...)` — полный 3D path (без изменений)
- Stage 6.5 в pipeline: создать `PhysicsEngine`, вызвать `analyze_2d()` по умолчанию, `analyze()` если 3D доступен
- Результат записать в `AnalysisReport.physics` (поле уже существует)
- `AnalysisReport.format()` уже рендерит physics поля

**Параллелизм:** PhysicsEngine (2D) запускается параллельно с BiomechanicsAnalyzer в Wave 2 `analyze_async()`.

**Затронутые файлы:**
- `ml/src/analysis/physics_engine.py` — добавить `analyze_2d()`
- `ml/src/pipeline.py` — wire PhysicsEngine в stage 6.5, parallel в Wave 2

### 5. Удалить Local GPU path + Vast.ai client cleanup

**Проблема:** `detect_video_task` содержит local GPU fallback (строки 514+). Мёртвый код. Vast.ai client без pooling/retry, мёртвый sync код.

**Решение:**

5a. Удалить local GPU path:
- Удалить блок `# --- Local path (GPU on this machine) ---` (строки 514-650)
- Убрать условие `if settings.vastai.api_key.get_secret_value()` — всегда remote path
- Startup validation: `RuntimeError` если `VASTAI_API_KEY` не задан
- Обновить docstring: "Requires VASTAI_API_KEY"

5b. Vast.ai client cleanup:
- Удалить sync мёртвый код: `process_video_remote()` и `_route_request()` (client.py строки 48-66, 102-164)
- Shared `httpx.AsyncClient` с connection pooling
- Разделить timeout: `ROUTE_TIMEOUT = 30` vs `WORKER_TIMEOUT = 600`
- Добавить retry на route failures (exponential backoff, 3 attempts)

5c. Config cleanup:
- Упростить `max_jobs` ternary (строки 815-819) — всегда `worker_max_jobs_remote`
- Удалить или репурпозить `worker_max_jobs` (local, больше не нужен)

**Затронутые файлы:**
- `backend/app/worker.py` — удалить local GPU, startup validation, max_jobs
- `backend/app/vastai/client.py` — shared client, retry, split timeout, удалить sync код
- `backend/app/config.py` — убрать `worker_max_jobs` или репурпозить

### 6. Качество метрик — Research closed, improvements documented

**Проблема:** Airtime определяется CoM parabola fitting. OOFSkate метод неизвестен.

**Исследование завершено:** OOFSkate НЕ использует ice plane detection. Prof. Hosoi (MIT): *"None of those rely on depth."* Наш 2D подход — правильный и валидирован (Webering et al., CVPR 2021). Парабола даёт pixel-to-meter scale через `k = -g/(2a)`.

**Улучшения для future iterations (не MVP):**
- de Leva body segment proportions для более точного CoM (вместо keypoint average)
- Ankle keypoint Y-velocity для точного takeoff/landing detection (+5-15% flight time)
- Gravity self-calibration из parabola coefficient (вместо ad-hoc pixel-to-meter)

**Ice plane detection: <10% улучшение для airtime. Не инвестировать.**

**Затронутые файлы:** Нет (research conclusion, не код)

### 7. Pipeline parallelism — enhanced analyze_async

**Проблема:** Все стадии выполняются последовательно. DTW запускается после Metrics (не нужен sequentually).

**Решение:** Enhanced wave-based `analyze_async()`:

```
Wave 0 (sequential):  Stages 1-3 (extract, normalize, smooth) + pre-compute CoM
Wave 1 (parallel):    Phase Detection [CPU] + Reference Load [I/O] + 3D Lift [GPU, if enabled]
Wave 2 (parallel):    Metrics + DTW + PhysicsEngine(2D) [all CPU, GIL released by NumPy/Numba]
Wave 3 (sequential):  Recommender + Score [< 1ms]
```

- DTW перемещается из sequential-after-Metrics в Wave 2 parallel
- PhysicsEngine (2D) запускается параллельно с Metrics в Wave 2
- Используется `asyncio.gather()` + `run_in_executor(None, ...)` — ThreadPoolExecutor достаточен (NumPy/Numba release GIL)
- ProcessPoolExecutor/Ray — overkill для single-machine single-GPU pipeline

**Теоретический выигрыш:** 0.3-0.5s на pipeline 3-5s (extraction = 98.9% времени на CPU).

**Затронутые файлы:**
- `ml/src/pipeline.py` — реструктурировать `analyze_async()`, Wave 2 parallel

## Файлы изменений

| Файл | Изменение |
|------|-----------|
| `ml/src/analysis/element_defs.py` | `rotations: float`, обновить значения, `is_jump()` |
| `ml/src/analysis/metrics.py` | Убрать axel хак `+0.5` (строки 375-377) |
| `ml/src/analysis/jump_classifier.py` | Убрать axel хак `+0.5` (строки 44-48) |
| `ml/src/alignment/motion_dtw.py` | 33 → `poses.shape[1]`, docstrings |
| `ml/src/alignment/aligner.py` | 33 → `poses.shape[1]`, docstrings |
| `ml/src/visualization/pipeline.py` | `build_layers()` — registry + LEVEL_PRESETS |
| `ml/src/visualization/comparison.py` | Унифицировать `_build_layers()` с registry |
| `ml/src/analysis/physics_engine.py` | Добавить `analyze_2d()` |
| `ml/src/pipeline.py` | Wire PhysicsEngine в stage 6.5, Wave 2 parallel |
| `backend/app/worker.py` | Удалить local GPU, startup validation, max_jobs |
| `backend/app/vastai/client.py` | Shared client, retry, split timeout, удалить sync |
| `backend/app/config.py` | Убрать/репурпозить `worker_max_jobs` |

Docstrings-only (33→17 / `(N, 33, 2)` → `(N, num_joints, 2)`):
- `ml/src/analysis/element_segmenter.py`
- `ml/src/analysis/phase_detector.py`
- `ml/src/detection/pose_tracker.py`
- `ml/src/detection/spatial_reference.py`

## Порядок выполнения

1. **Axel rotations bug** — самый критический, ломает классификацию (2 файла с хаком)
2. **DTW 33→runtime detection** — ломает DTW alignment (6+ мест в 2 файлах + docstrings)
3. **VizPipeline layers** — MVP не покажет trails/velocity без этого
4. **Remove local GPU + Vast.ai cleanup** — мёртвый код, чистота, connection pooling
5. **PhysicsEngine 2D fallback + wiring** — добавляет value, parallel в Wave 2
6. **Pipeline parallelism** — enhanced analyze_async, DTW parallel с Metrics
7. **Metric quality improvements** — future: de Leva, ankle velocity, gravity self-cal

## Критерии приёмки

- [ ] `axel.rotations == 1.5` (float), `compute_under_rotation` для axel считает от 540°
- [ ] Нет хака `+0.5` ни в metrics.py, ни в jump_classifier.py
- [ ] `MotionDTWAligner` работает с `(N, 17, 2)` — никаких hardcoded 33
- [ ] `align_with_keyframes()` использует `poses.shape[1]`, не `list(range(33))`
- [ ] `VizPipeline(layer=1)` показывает skeleton + velocity + trails
- [ ] `VizPipeline(layer=2)` показывает skeleton + velocity + trails + joint angles + vertical axis
- [ ] `VizPipeline(layer=3)` показывает полный HUD + blade indicator
- [ ] `detect_video_task` падает с понятной ошибкой если нет `VASTAI_API_KEY`
- [ ] Нет local GPU fallback кода в worker.py
- [ ] Vast.ai client использует shared `httpx.AsyncClient` с connection pooling
- [ ] `AnalysisReport.physics` содержит `jump_height`, `flight_time`, `takeoff_velocity`, `fit_quality`
- [ ] `PhysicsEngine.analyze_2d()` работает с `(N, 17, 2)` poses
- [ ] DTW + Metrics + Physics запускаются параллельно в Wave 2 `analyze_async()`
- [ ] Все существующие тесты проходят
- [ ] Новые тесты для каждого фикса

## Исследования (brainstorm report)

Полный отчёт 5 research-агентов: `docs/specs/2026-05-22-ml-pipeline-brainstorm-report.md`

Ключевые находки:
- **OOFSkate** НЕ использует ice plane detection (Prof. Hosoi, MIT)
- **CoM parabola** валидирован (Webering et al., CVPR 2021)
- **PhysicsEngine** требует 3D — нужен `analyze_2d()` fallback
- **DTW баг** в `aligner.py` тоже (не только `motion_dtw.py`)
- **Axel хак** в `jump_classifier.py` тоже (не только `metrics.py`)
- **Parallel rendering** невозможен (numpy race conditions) — sequential per frame
- **Vast.ai client** — нет pooling, нет retry, мёртвый sync код