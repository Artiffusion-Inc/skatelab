# ML Pipeline Production Readiness — Brainstorm Report

> Дата: 2026-05-22
> Метод: 5 параллельных research-агентов + synthesis
> Исходная спека: `docs/specs/2026-05-22-ml-pipeline-production-readiness-design.md`

## Краткие выводы

1. **Axel hack шире чем в спеке** — `+0.5` хак в 2 местах (metrics.py + jump_classifier.py), оба нужно убрать
2. **33→17 тоже шире** — `aligner.py` содержит те же баги + docstrings в 5+ файлах
3. **PhysicsEngine требует 3D** — `analyze()` принимает `(N,17,3)`, нужен 2D fallback
4. **Parallel rendering слоёв невозможен** — numpy не thread-safe для concurrent writes
5. **OOFSkate НЕ использует ice plane detection** — подтверждено Prof. Hosoi (MIT)
6. **Pipeline параллелизм** — выигрыш 0.3-0.5s (extraction = 98.9% времени)
7. **Vast.ai client** — нет connection pooling, нет retry, мёртвый sync код

---

## 1. Axel Rotations — расширенный аудит

### Найденные проблемы (больше чем в спеке)

| # | Файл | Строка | Проблема | Severity |
|---|------|--------|----------|----------|
| 1 | `element_defs.py` | 27 | `rotations: int` — тип усекает axel | Critical |
| 2 | `element_defs.py` | 261 | `rotations=int(1.5)` = 1 | Critical |
| 3 | `metrics.py` | 375-377 | Axel hack `+ 0.5` — сломается при float | Critical |
| 4 | **`jump_classifier.py`** | **44-48** | **Второй axel hack `+ 0.5`** — НЕ в спеке | **Critical** |
| 5 | `element_defs.py` | — | Нет double/triple jump элементов | Design gap |

**Важное уточнение:** При `rotations: float`:
- `int(2.5)` = 2, hack +0.5 = 2.5 — работает случайно
- Но если `rotations=2.5` (float), hack +0.5 = 3.0 — **НЕВЕРНО**

Следовательно: удаление хаков обязательно при переходе на float.

### Дизайн-пробел: ELEMENT_DEFS

Текущий словарь содержит только single-rotation версии прыжков. `classify_jump()` использует proximity matching, что даёт слабую классификацию для double/triple (rotation_count=2.0 vs rotations=1.0 → diff=1.0 → score=0.3).

**Для MVP:** не блокирует. Single axel — самый частый кейс.

---

## 2. DTW 33→17 — расширенный аудит

### Все локации с hardcoded 33

| Файл | Строки | Что | Fix |
|------|--------|------|-----|
| `motion_dtw.py` | 131 | `joints = list(range(33))` | `poses.shape[1]` или константа |
| `motion_dtw.py` | 388 | `np.zeros((..., 33, 2))` padding | `poses.shape[1]` |
| `motion_dtw.py` | 393 | `np.zeros((..., 33, 2))` output | `poses.shape[1]` |
| **`aligner.py`** | **51, 91** | **`list(range(33))`** — НЕ в спеке | `poses.shape[1]` |
| **`aligner.py`** | **223** | **`np.zeros((..., 33, 2))`** — НЕ в спеке | `poses.shape[1]` |
| Multiple | 121,123,125, 40-42,83-85, 213,218, 92,231,237, 31,81,401, 195,312, 223 | Docstrings `(N, 33, 2)` | Обновить на `(N, 17, 2)` |

### Рекомендация: `poses.shape[1]` вместо хардкода 17

```python
# Вместо:
joints = list(range(17))
np.zeros((..., 17, 2))

# Лучше:
joints = list(range(poses.shape[1]))  # runtime detection
np.zeros((..., poses.shape[1], 2))
```

Или определить константу:
```python
H36M_NUM_KEYPOINTS = 17  # в ml/src/types.py
```

**Уже корректно:** `smoothing.py` валидирует `num_joints not in (17, 33)` — поддерживает оба формата.

### H3.6M формат подтверждён

17 keypoints. Нет "+1 background node". 33 — это BlazePose формат, copy-paste ошибка в DTW коде.

---

## 3. PhysicsEngine — проблема с 3D

### Критическое уточнение к спеке

Спека говорит: "вызвать `analyze()` с 2D poses + phases + fps". **Но `PhysicsEngine.analyze()` требует 3D:**

```python
def analyze(self, poses_3d: np.ndarray,  # (N, 17, 3) ← 3D!
            takeoff_idx: int, landing_idx: int, fps: float) -> PhysicsResult
```

`calculate_center_of_mass()`, `calculate_moment_of_inertia()`, `calculate_angular_momentum()` — все работают с `(N,17,3)`.

### Решение: 2D fallback mode

`calculate_com_trajectory()` в `geometry.py` работает с NormalizedPose `(N,17,2)`. Можно:

1. Создать `PhysicsEngine.analyze_2d()` — CoM + jump height + flight time из 2D
2. Пропустить moment of inertia и angular momentum (требуют 3D)
3. При доступности 3D — полный `analyze()`

```python
def analyze_2d(self, poses_2d, takeoff_idx, landing_idx, fps):
    """2D approximation: CoM trajectory + jump height + flight time."""
    com = calculate_com_trajectory(poses_2d)  # works on (N,17,2)
    flight_com = com[takeoff_idx:landing_idx+1, 1]
    jump_height = float(np.max(flight_com) - np.min(flight_com))
    flight_time = (landing_idx - takeoff_idx) / fps
    return {
        "jump_height": jump_height,
        "flight_time": flight_time,
        "takeoff_velocity": ...,  # derivable from CoM
        "avg_inertia": None,      # requires 3D
        "fit_quality": ...,       # R² from parabola fit
    }
```

---

## 4. VizPipeline — параллельный рендеринг

### Параллельный рендеринг слоёв на одном фрейме НЕ возможен

- numpy arrays не thread-safe для concurrent writes
- `cv2.line`, `cv2.putText` release GIL — race conditions на C++ уровне
- Copy-then-composite возможен, но дорогой (~6MB/frame × N layers × 30fps)
- Ни один open-source проект (MMPose, AlphaPose, DeepLabCut) не делает parallel intra-frame rendering

### Правильная параллельность

1. **Frame-level** — несколько фреймов одновременно (processing pool)
2. **Pre-compute** — векторизовать trail/velocity данные из полного массива poses до frame loop
3. **Sequential layer rendering** внутри фрейма — industry standard

### Рекомендуемый паттерн: Declarative config с registry

```python
LAYER_REGISTRY: dict[str, type[Layer]] = {
    "trail": TrailLayer,
    "velocity": VelocityLayer,
    "joint_angle": JointAngleLayer,
    "vertical_axis": VerticalAxisLayer,
    "hud": HUDLayer,
    "blade": BladeLayer,
    "skeleton": SkeletonLayer,
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

Объединяет две существующие системы (`VizPipeline.build_layers()` + `ComparisonRenderer._build_layers()`).

### Pre-compute оптимизация (future)

TrailLayer и VelocityLayer хранят per-frame state (`_trail_2d`, `_vel_history`). Можно векторизовать:

```python
# До frame loop:
trail_positions = poses_norm[max(0, N-trail_length):N+1]  # vectorized slice
velocity_vectors = np.diff(poses_norm, axis=0)              # vectorized diff
```

Это убирает list append/pop overhead и делает слои stateless → frame-level parallelism.

---

## 5. Ice Plane Detection — исследования

### OOFSkate НЕ использует ice plane detection

Prof. Hosoi (MIT, советник OOFSkate):

> "In figure skating, you need to understand: How high did they jump, how many rotations, and how well did they land? **None of those rely on depth.** He's found an application that pose estimators do really well, and that doesn't pay a penalty for the things they do badly."

Это подтверждает: наш 2D-only подход — **правильный**, не ограничение.

### Наш метод валидирован

Webering et al. (CVPR 2021) опубликовали тот же метод: CoM parabola fitting с gravity self-calibration. Коэффициент `a` в `y(t) = at² + v₀t + y₀` даёт pixel-to-meter scale: `k = -g/(2a)`.

### Топ-3 улучшения для airtime

| # | Метод | Улучшение | Сложность | Блокирует MVP? |
|---|-------|-----------|-----------|----------------|
| 1 | Улучшить CoM parabola (de Leva пропорции, gravity self-cal) | 10-25% на jump height | Low | Нет |
| 2 | Ankle keypoint velocity для takeoff/landing | 5-15% на flight time | Low | Нет |
| 3 | Rink homography (если видны маркировки) | 5-10% на jump height | Medium | Нет |

### Ice plane detection: <10% улучшение для airtime

**Вывод:** Инвестировать в ice plane detection для airtime НЕ стоит. Спека была права — отложить в research task.

### Ключевые ссылки

- Webering et al., CVPR 2021 — [PDF](https://openaccess.thecvf.com/content/CVPR2021W/CVPM/papers/Webering_Markerless_Camera-Based_Vertical_Jump_Height_Measurement_Using_OpenPose_CVPRW_2021_paper.pdf)
- Bruening et al., PLOS ONE 2018 — [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC6248918)
- HockeyRink dataset, ACM MMSys 2025 — [DOI](https://dl.acm.org/doi/abs/10.1145/3712676.3718338)
- FSBench, CVPR 2025 — [PDF](https://openaccess.thecvf.com/content/CVPR2025/papers/Gao_FSBench_A_Figure_Skating_Benchmark_for_Advancing_Artistic_Sports_Understanding_CVPR_2025_paper.pdf)
- MIT News OOFSkate — [MIT](https://news.mit.edu/2026/3-questions-using-ai-help-olympic-skaters-land-quint-0210)

---

## 6. Pipeline Parallelism

### Профилирование (186 frames, 3.1s video)

| Stage | Time (s) | % |
|-------|----------|---|
| Extract & Track (GPU) | 69.85 | 98.9% |
| Normalize | 0.0012 | 0.002% |
| Smooth | 0.26 | 0.4% |
| Phase Detection | 0.49 | 0.7% |
| Metrics | 0.032 | 0.05% |
| DTW + Physics + Recommender | ~0.1 | ~0.1% |

GPU extraction доминирует. Параллелизм post-extraction стадий = выигрыш 0.3-0.5s на pipeline 3-5s.

### Dependency graph

```
Stage 1 (Extract) → Stage 2 (Normalize) → Stage 3 (Smooth)
                                                  ↓
                                          Stage 4 (Phase Detect)
                                                  ↓
                              ┌───────────────────┼───────────────────┐
                              ↓                   ↓                   ↓
                        Stage 5 (Metrics)   Stage 6 (DTW)      Stage 6.5 (Physics)
                              ↓                   ↓                   ↓
                              └───────────────────┼───────────────────┘
                                                  ↓
                                          Stage 7+8 (Recommend + Score)
```

**Stages 5+6+6.5 МОГУТ работать параллельно** после Stage 4.

### Рекомендуемая стратегия: Enhanced analyze_async

```python
# Wave 0 (sequential): Stages 1-3 + pre-compute CoM
# Wave 1 (parallel):   Phase Detection [CPU] + Reference Load [I/O] + 3D Lift [GPU, if enabled]
# Wave 2 (parallel):   Metrics + DTW + Physics [all CPU, GIL released by NumPy/Numba]
# Wave 3 (sequential): Recommend + Score [< 1ms]
```

**Почему не ProcessPoolExecutor/Ray:**
- NumPy, SciPy, Numba release GIL → ThreadPoolExecutor даёт настоящую параллельность
- Array serialization overhead для ProcessPool (хоть и небольшой)
- Ray — overkill для single-machine single-GPU
- Выигрыш < 0.5s не оправдывает сложность

### DTW: переместить в parallel с Metrics

Текущий код: DTW запускается после Metrics (sequential). DTW использует `normalized` (не `smoothed`) + `phases` + `reference` — все доступны после Wave 1. Можно запускать параллельно с Metrics в Wave 2.

---

## 7. Vast.ai Worker — дополнительные находки

### Local GPU код для удаления

| Что | Файл | Строки |
|-----|------|--------|
| Local GPU fallback block | `worker.py` | 514-650 |
| Docstring "runs locally on GPU" | `worker.py` | 6-7 |
| Conditional API key gate | `worker.py` | 470 |
| `max_jobs` ternary (local branch) | `worker.py` | 815-819 |
| Unused `worker_max_jobs` config | `config.py` | 152 |

### Мёртвый sync код

`process_video_remote()` и `_route_request()` в `client.py` (строки 48-66, 102-164) — никогда не вызываются из async worker.

### Connection pooling

Текущий код создаёт новый `httpx.AsyncClient` на каждый запрос → нет pooling, нет HTTP/2, TCP handshake каждый раз.

**Fix:** Shared module-level client:
```python
_async_client: httpx.AsyncClient | None = None

async def get_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(
            timeout=httpx.Timeout(600, connect=30.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _async_client
```

### Timeout разделение

Route resolution (~5s) и GPU inference (минуты) используют один `REQUEST_TIMEOUT=600`. Разделить:
```python
ROUTE_TIMEOUT = 30       # route resolution
WORKER_TIMEOUT = 600     # actual GPU inference
```

### Нет retry на route failures

Vast.ai SDK имеет exponential backoff. Наш код — нет. Рекомендация:
```python
@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
    retry=tenacity.retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
)
async def _async_route_request(endpoint_name, api_key): ...
```

### Startup validation VASTAI_API_KEY

Рекомендация: fail-fast при старте worker, не при запросе:
```python
async def startup(ctx: dict) -> None:
    settings = get_settings()
    if not settings.vastai.api_key.get_secret_value():
        raise RuntimeError("VASTAI_API_KEY is required. Set it in .env.")
```

---

## Обновления к исходной спеке

На основе findings, нужно обновить `2026-05-22-ml-pipeline-production-readiness-design.md`:

### Пункт 1 (Axel): добавить
- Удалить axel hack в `jump_classifier.py` строки 44-48 (НЕ только metrics.py)
- Обновить docstring: "rotations: float — axel = 1.5 оборота"

### Пункт 2 (DTW): расширить
- Добавить `aligner.py` строки 51, 91, 223 в список
- Заменить "4 места с 33" на "6+ мест в motion_dtw.py + aligner.py"
- Использовать `poses.shape[1]` вместо хардкода 17

### Пункт 4 (PhysicsEngine): уточнить
- `analyze()` требует 3D `(N,17,3)`, НЕ 2D
- Нужен `analyze_2d()` fallback для 2D-only pipeline
- При 2D: доступны jump_height, flight_time, takeoff_velocity, fit_quality
- При 2D: avg_inertia = None (требует 3D)

### Пункт 5 (Local GPU): расширить
- Добавить удаление sync мёртвого кода в client.py
- Добавить startup validation VASTAI_API_KEY
- Добавить connection pooling в Vast.ai client
- Добавить разделение timeout (route 30s vs worker 600s)
- Добавить retry на route failures

### Пункт 3 (VizPipeline): дополнить
- Использовать Declarative config с registry (LAYER_REGISTRY + LEVEL_PRESETS)
- Объединить с ComparisonRenderer._build_layers()
- Pre-compute оптимизация — future task, не MVP

### Новый пункт: Pipeline parallelism
- DTW перемещается в Wave 2 параллельно с Metrics
- PhysicsEngine (2D) тоже в Wave 2
- Enhanced analyze_async — достаточная стратегия

### Новый пункт: Airtime quality improvements (не блокирует MVP)
- de Leva body segment proportions для CoM
- Ankle keypoint velocity для takeoff/landing detection
- Gravity self-calibration (k = -g/(2a)) для pixel-to-meter
