# RF-DETR Migration Design

Дата: 2026-05-24
Статус: Revised (после multi-agent research)
Связанный спека: [IP Audit](2026-05-24-ip-audit-design.md)

## Проблема

YOLOv8n (AGPL-3.0 веса) — единственный AGPL-компонент в прод-рантайме. Ultralytics Python-пакет (AGPL-3.0) — зависимость прод-кода. Оба блокируют коммерческую чистоту при due diligence.

Решение: заменить на RF-DETR (Apache 2.0) + удалить ultralytics полностью.

## Multi-Agent Research: ключевые находки

5 специализированных агентов исследовали совместимость, доменную пригодность, параллелизм, лицензии и паттерны миграции. Итоги:

### ONNX Runtime совместимость — БЛОКЕРОВ НЕТ

- Opset 17 полностью совместим с onnxruntime-gpu >=1.24.4
- Нет кастомных ops — только стандартные (Conv, Resize, MatMul и т.д.)
- CUDA 12 compat libs работают (те же что и для MogaNet-B)
- Dynamic batch ONNX: исправлен в rfdetr >=1.7.0 (раньше cls_token хардкодил B=1)
- Python 3.13 export: ошибка bfloat16, обходится rfdetr >=1.7.0 или Python 3.12
- INT8 ONNX медленнее FP32 на GPU — использовать FP32
- FP16 TensorRT имеет проблемы с LayerNorm — для onnxruntime-gpu FP32 безопасно

### Доменная пригодность — КРИТИЧЕСКИЕ ОГРАНИЧЕНИЯ

**RF-DETR-Nano (384x384) НЕ подходит для фигурного катания:**
- Фигурист на дальнем плане: 20-40px в кадре 1920x1080 → 4-8px при ресайзе до 384x384
- Это ниже порога детекции для любой модели
- Официальные бенчмарки НЕ публикуют AP_S (small object AP)

**Минимум: RF-DETR-Small (512x512). Оптимально: RF-DETR-Medium (576x576).**

| Модель | Вход | COCO AP50:95 | Params | ONNX ~размер | RTX 3050 Ti FPS (оценка) |
|--------|------|-------------|--------|-------------|-------------------------|
| YOLOv8n | 640x640 | 37.4 | 3.2M | ~6 MB | 67-125 |
| RF-DETR-N | 384x384 | 48.4 | 30.5M | ~120 MB | 40-67 |
| RF-DETR-S | 512x512 | 53.0 | 32.1M | ~128 MB | 30-50 |
| RF-DETR-M | 576x576 | 54.7 | 33.7M | ~135 MB | 25-40 |

- CPU fallback: RF-DETR-N ~200ms/frame vs YOLOv8n ~20ms/frame — **10x медленнее, неприемлемо для CPU-only**
- FP16 LayerNorm нестабильность — подтверждено для TensorRT, onnxruntime-gpu FP32 OK
- Нет спортивных бенчмарков RF-DETR, ни одного проекта фигурного катания на DETR-family

### Лицензии — ЧИСТО С ОГОВОРКАМИ

| Модель | Лицензия | Коммерция |
|--------|----------|-----------|
| RF-DETR N/S/M/L (detection) | Apache 2.0 | Да, полностью |
| RF-DETR-XL/2XL (detection) | PML 1.0 | НЕТ — привязка к аккаунту Roboflow |
| RF-DETR-Seg (все размеры) | Apache 2.0 | Да |
| DINOv2 backbone | Apache 2.0 (с авг 2023) | Да (был CC BY-NC, релецензирован) |
| COCO-pretrained веса | Apache 2.0 + CC BY 4.0 | Да |
| Objects365-pretrained веса | "Academic only" dataset | N/S/M/L — COCO-pretrained, не Objects365 |

**Community ONNX экспорт (PierreMarieCurie/rf-detr-onnx) N-L моделей = производная Apache 2.0 — безопасно.**

### Pipeline параллелизм — СТРАТЕГИЯ

1. **Detection stride + интерполяция** — высший ROI (1.5-2x throughput, 2 дня работы)
   - Detect каждые N кадров, линейная интерполяция bboxes для промежуточных
   - Независимо от выбора модели
   - Для фигурного катания (30fps, плавное движение): stride=4, bbox drift <2px

2. **Staged pipeline: detect-all → pose-all** — лучшее использование GPU
   - Сериализовать стадии, не пытаться параллелить на одной GPU
   - CUDA stream параллелизм бесполезен на RTX 3050 Ti (4GB) — kernels конкурируют за SM
   - Release detector VRAM после detection phase → больше памяти для MogaNet-B

3. **Dynamic batch ONNX** — исправлен в rfdetr >=1.7.0, но для video pipeline batch=1 достаточен

4. **VRAM бюджет RTX 3050 Ti:**
   - RF-DETR-S + MogaNet-B ≈ 1.2-1.8 GB — помещается
   - RF-DETR-S + MogaNet-B + DeepSORT ≈ 1.5-2.1 GB — плотно, но feasible
   - Staged release (del detector after detection) — safest

### Миграция — 5 КРИТИЧЕСКИХ GOTCHA

| # | Проблема | Тихий провал? | Фикс |
|---|----------|---------------|------|
| 1 | sigmoid, не softmax на логитах | Да — неверные детекции | `1 / (1 + exp(-logits.clip(-88,88)))` |
| 2 | Drop last logit column (no-object) | Да — IndexError или подавленные scores | `logits[:, :-1]` — для COCO (1, 300, 81) → (1, 300, 80) |
| 3 | cxcywh normalized → xyxy pixel | Да — bbox'ы сильно смещены | `(cx ± w/2) * orig_W`, `(cy ± h/2) * orig_H` |
| 4 | ImageNet normalize, не /255 | Да — тишина, accuracy collapse | mean/std + BGR→RGB |
| 5 | Remove letterbox, использовать resize | Да — координаты неправильные | Прямой resize, не letterbox padding |

## Решение: пересмотренный дизайн

### Выбор модели

**RF-DETR-Small (512x512)** — минимум для фигурного катания. RF-DETR-Medium (576x576) — оптимально, если FPS достаточен.

Обоснование:
- Nano (384x384) отброшен — слишком мало пикселей для далёких фигуристов
- Small (512x512) — компромисс: 2.7x больше пикселей чем Nano, COCO AP 53.0 (+15.6 vs YOLOv8n)
- Base (640x640) — максимальное разрешение, но 29M params, медленнее

Бенчмарк: Small vs Medium на skating видео. Если Medium FPS ≥ 25 — берём Medium.

### Текущая интеграция YOLO

**Единственный потребитель:** `ml/src/detection/person_detector.py`

```
Video → PersonDetector (YOLOv8n ONNX) → crop → MogaNetBatch (ONNX)
```

**Файлы с ссылками на YOLO:**

| Файл | Что делает |
|------|-----------|
| `ml/src/detection/person_detector.py` | PersonDetector класс, ONNX inference |
| `ml/gpu_server/server.py` | R2 path `models/yolov8n.onnx`, startup check |
| `ml/pyproject.toml` | `ultralytics>=8.0.0` dependency |
| `ml/yolov8n.pt` | PyTorch веса (удалить) |
| `ml/scripts/create_yolo_subset.py` | Создание YOLO датасета (удалить) |
| `ml/scripts/train_yolo26_pose.py` | Обучение YOLO pose (удалить) |
| `ml/scripts/train_yolo26n_distill.py` | Дистилляция YOLO (удалить) |

**API PersonDetector** (не меняется):

```python
class PersonDetector:
    def __init__(self, model_path: str | Path, confidence: float = 0.5)
    def detect_frame(self, frame: np.ndarray) -> BoundingBox | None
    def detect_video(self, video_path: Path) -> list[BoundingBox]
    def detect_first_frame(self, video_path: Path) -> BoundingBox | None
```

## RF-DETR спецификации (пересмотренные)

| Аспект | RF-DETR-Small | RF-DETR-Medium |
|--------|--------------|----------------|
| Параметры | ~32M | ~34M |
| COCO AP50:95 | 53.0 | 54.7 |
| COCO AP50 | 72.1 | 73.6 |
| Лицензия | Apache 2.0 | Apache 2.0 |
| Вход | (1, 3, 512, 512) float32 | (1, 3, 576, 576) float32 |
| Препроцессинг | ImageNet normalize | ImageNet normalize |
| Выход boxes | (1, 300, 4) cxcywh norm | (1, 300, 4) cxcywh norm |
| Выход logits | (1, 300, 81) | (1, 300, 81) |
| ONNX opset | 17 | 17 |
| Latency (T4 TRT FP16) | 3.5 ms | 4.4 ms |
| Latency (3050 Ti ORT FP32 est) | 15-25 ms | 20-30 ms |

**Источник ONNX весов:** Самостоятельный экспорт через `rfdetr >=1.7.0` (Python 3.12).
Альтернатива: `PierreMarieCurie/rf-detr-onnx` на HuggingFace (но rfdetr 1.4.1, нет Small/Medium).

## Отличия YOLO → RF-DETR в пост-обработке

### Препроцессинг

```python
# YOLOv8n (было): letterbox + /255
img, (r, _), (pad_w, pad_h) = _letterbox(frame)
blob = img.transpose(2,0,1).astype(np.float32) / 255.0

# RF-DETR (стало): resize + BGR→RGB + ImageNet normalize
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
resized = cv2.resize(rgb, (_INPUT_W, _INPUT_H))
blob = resized.astype(np.float32) / 255.0
blob = (blob - IMAGENET_MEAN) / IMAGENET_STD
blob = blob.transpose(2, 0, 1)[np.newaxis]  # (1, 3, H, W)
```

### Пост-обработка

```python
# YOLOv8n (было): (1, 84, 8400) → transpose → filter person
pred = outputs[0][0].T  # (8400, 84): xywh + 80 class scores
person_scores = pred[:, 4 + PERSON_CLASS]

# RF-DETR (стало): два тензора, 5 критических шагов
boxes = outputs[0].squeeze(0)          # (300, 4): cxcywh normalized
logits = outputs[1].squeeze(0)[:, :-1] # (300, 80): DROP last col (no-object)

# Step 1: numerically stable sigmoid (NOT softmax)
scores_all = 1.0 / (1.0 + np.exp(-logits.clip(-88, 88)))

# Step 2: filter person class
person_scores = scores_all[:, PERSON_CLASS]
mask = person_scores > confidence

# Step 3: cxcywh normalized → xyxy pixel
cx, cy, w, h = boxes[mask].T
x1 = (cx - w / 2) * orig_W
y1 = (cy - h / 2) * orig_H
x2 = (cx + w / 2) * orig_W
y2 = (cy + h / 2) * orig_H
xyxy = np.stack([x1, y1, x2, y2], axis=1)

# Step 4: top-1 selection (single-person) or NMS (multi-person)
best_idx = person_scores[mask].argmax()

# Step 5: clip to frame bounds
```

## Изменения по файлам

### Модифицируемые

1. **`ml/src/detection/person_detector.py`** — полная переписка:
   - Удалить `_letterbox()`, добавить `_preprocess()` с ImageNet normalize + BGR→RGB
   - `_nms()` оставить (работает для любого формата bbox)
   - Переписать `detect_frame()`: sigmoid, drop last logit, cxcywh→xyxy, denormalize
   - Добавить warmup inference на модельной загрузке
   - `_DEFAULT_MODEL` → `data/models/rf_detr_small.onnx`
   - `_INPUT_SIZE` → конфигурируемый (512 для Small, 576 для Medium)

2. **`ml/gpu_server/server.py`** — заменить:
   - `YOLO_MODEL_PATH` → `RF_DETR_MODEL_PATH`
   - R2 key: `models/yolov8n.onnx` → `models/rf_detr_small.onnx`
   - Startup check: обновить имя модели

3. **`ml/pyproject.toml`** — удалить `ultralytics>=8.0.0` из dependencies

4. **`data/models/models.manifest.json`** — добавить записи `rf_detr_small` и `rf_detr_medium`

5. **`ml/scripts/download_ml_models.py`** — добавить скачивание RF-DETR ONNX

### Удаляемые

6. **`ml/yolov8n.pt`** — PyTorch веса YOLOv8n
7. **`ml/scripts/create_yolo_subset.py`** — создание YOLO-датасета
8. **`ml/scripts/train_yolo26_pose.py`** — обучение YOLO pose
9. **`ml/scripts/train_yolo26n_distill.py`** — дистилляция YOLO

### Новые файлы

10. **`ml/scripts/benchmark_detector.py`** — сравнение RF-DETR Small vs Medium на skating видео
11. **`ml/scripts/export_rf_detr.py`** — экспорт ONNX из PyTorch (rfdetr >=1.7.0, Python 3.12)

### Тесты

12. **`ml/tests/detection/test_person_detector.py`** — обновить docstrings, добавить тесты:
    - sigmoid vs softmax (проверить что используется sigmoid)
    - drop last logit column
    - cxcywh → xyxy conversion
    - ImageNet normalization (mean/std)

## Бенчмарк-стратегия

Скрипт `benchmark_detector.py` сравнивает:

| Метрика | Как измеряем |
|---------|-------------|
| FPS | `time.perf_counter()` на 100 кадров |
| Детекция маленьких объектов | Фигуристы на дальнем плане (20-40px) |
| Качество crop'а | Визуальная проверка: далеко/близко, вращения, отражения льда |
| Recall | % кадров где детекция успешна (сравнение с YOLOv8n baseline) |

Тестируемые модели:
- `rf_detr_small.onnx` (512x512, ~32M params)
- `rf_detr_medium.onnx` (576x576, ~34M params)

Критерий успеха: RF-DETR-Small recall на маленьких объектах ≥ YOLOv8n, FPS ≥ 25.

## Pipeline оптимизация (параллельно с миграцией)

### Detection stride + интерполяция

Detect каждые 4 кадра, линейная интерполяция bboxes для промежуточных. Внедряется в `pose_extractor.py` и `batch_extractor.py`.

```python
DETECTION_STRIDE = 4

# Phase 1: Detect every Nth frame
for i, frame in enumerate(frames):
    if i % DETECTION_STRIDE == 0:
        bbox = detector.detect_frame(frame)
        detections[i] = bbox

# Phase 2: Interpolate missing frames
for i in range(len(frames)):
    if i not in detections:
        detections[i] = _lerp_bbox(detections, i)
```

Impact: detection calls ↓ 75%, throughput ↑ 1.5-2x.

### Staged pipeline (detect-all → release → pose-all)

```python
# Phase 1: All detections (RF-DETR loaded)
detections = detect_all_frames(video_path)
del detector  # Release VRAM (~150-250MB)
# Phase 2: All pose inference (full VRAM for MogaNet-B)
keypoints = moganet.infer_batch(crops, bboxes)
```

Impact: VRAM headroom для MogaNet-B, исключает OOM на RTX 3050 Ti.

## Порядок миграции

1. Экспортировать RF-DETR-Small и Medium ONNX (rfdetr >=1.7.0, Python 3.12)
2. Переписать `person_detector.py` (RF-DETR inference, все 5 gotcha)
3. Обновить `gpu_server/server.py`
4. Удалить ultralytics из pyproject.toml
5. Удалить YOLO скрипты и веса
6. Обновить manifest + download script
7. Написать benchmark_detector.py
8. Запустить бенчмарк на skating видео (Small vs Medium)
9. Выбрать модель по результатам
10. Добавить detection stride + интерполяцию в pose_extractor.py
11. Обновить тесты
12. Проверить полный пайплайн: video → detect → pose → metrics

## Риски и митигация

| Риск | Серьёзность | Митигация |
|------|------------|-----------|
| RF-DETR-Small хуже YOLOv8n на маленьких объектах (512 vs 640) | HIGH | Бенчмарк на skating видео; fallback на Medium (576) |
| CPU fallback 10x медленнее | HIGH | GPU-only inference (уже требование проекта) |
| Тихий провал пост-обработки (sigmoid, drop last col) | CRITICAL | 5 отдельных тестов на каждый gotcha |
| RF-DETR FP16 LayerNorm деградация | MEDIUM | FP32 ONNX inference только |
| Размер модели (~130MB vs ~6MB) | MEDIUM | Staged pipeline: release detector после detection |
| Нет готовых ONNX Small/Medium на HF | LOW | Скрипт экспорта (rfdetr >=1.7.0) |
| Roboflow меняет лицензию на будущие модели | LOW | N-L уже Apache 2.0, нельзя отозвать |

## IP-компоненты после миграции

| Компонент | Лицензия | Статус |
|-----------|----------|--------|
| RF-DETR-S/M веса (COCO) | Apache 2.0 | Чисто |
| DINOv2 backbone | Apache 2.0 | Чисто (релицензирован из CC BY-NC в авг 2023) |
| RF-DETR код | Apache 2.0 | Не в проде (только ONNX) |
| PersonDetector код | Собственная | Чисто |
| ONNX Runtime | MIT | Чисто |
| ~~YOLOv8n веса~~ | ~~AGPL-3.0~~ | Удалено |
| ~~ultralytics Python~~ | ~~AGPL-3.0~~ | Удалено |
