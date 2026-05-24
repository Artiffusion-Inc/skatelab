# RF-DETR Migration Design

Дата: 2026-05-24
Статус: Approved
Связанный спека: [IP Audit](2026-05-24-ip-audit-design.md)

## Проблема

YOLOv8n (AGPL-3.0 веса) — единственный AGPL-компонент в прод-рантайме. Ultralytics Python-пакет (AGPL-3.0) — зависимость прод-кода. Оба блокируют коммерческую чистоту при due diligence.

Решение: заменить на RF-DETR (Apache 2.0) + удалить ultralytics полностью.

## Текущая интеграция YOLO

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

## RF-DETR спецификации

| Аспект | RF-DETR Nano | RF-DETR Base |
|--------|-------------|--------------|
| Параметры | ~9M | ~29M |
| COCO mAP | ~48 | ~53 |
| Лицензия | Apache 2.0 | Apache 2.0 |
| Вход | (1, 3, 640, 640) float32 | (1, 3, 640, 640) float32 |
| Препроцессинг | ImageNet normalize | ImageNet normalize |
| Выход boxes | (1, N, 4) cxcywh norm | (1, N, 4) cxcywh norm |
| Выход logits | (1, N, 91) | (1, N, 91) |
| Разрешение | Кратно 32 | Кратно 32 |

**Источник ONNX весов:** `PierreMarieCurie/rf-detr-onnx` на HuggingFace.
Альтернатива: самостоятельный экспорт через `rfdetr` Python-пакет.

## Отличия YOLO → RF-DETR в пост-обработке

### Препроцессинг

```python
# YOLOv8n (было): letterbox + /255
img = letterbox(frame, 640)
blob = img.transpose(2,0,1).astype(np.float32) / 255.0

# RF-DETR (стало): resize + ImageNet normalize + BGR→RGB
img = cv2.resize(frame, (640, 640))
img = img[:, :, ::-1].astype(np.float32) / 255.0  # BGR→RGB
img = (img - MEAN) / STD  # ImageNet normalize
blob = img.transpose(2, 0, 1)[np.newaxis]
```

MEAN = `[0.485, 0.456, 0.406]`, STD = `[0.229, 0.224, 0.225]`

### Пост-обработка

```python
# YOLOv8n (было): (1, 84, 8400) → transpose → filter person
pred = outputs[0][0].T  # (8400, 84): xywh + 80 class scores
person_scores = pred[:, 4 + PERSON_CLASS]

# RF-DETR (стало): два тензора
boxes = outputs[0][0]   # (N, 4): cxcywh normalized
logits = outputs[1][0]   # (N, 91): class logits
probs = sigmoid(logits)
person_scores = probs[:, PERSON_CLASS]  # COCO class 0
# Фильтр по confidence → NMS → cxcywh → xyxy → denormalize
```

Ключевое отличие: RF-DETR выдаёт **нормализованные** cxcywh (0-1), YOLO — пиксельные xywh. Denormalize: `xyxy * (W, H, W, H)`.

## Изменения по файлам

### Модифицируемые

1. **`ml/src/detection/person_detector.py`** — полная переписка:
   - Удалить `_letterbox()`, добавить `_preprocess()` с ImageNet normalize
   - `_nms()` оставить (работает для любого формата bbox)
   - Переписать `detect_frame()`: RF-DETR output format, sigmoid, cxcywh→xyxy, denormalize
   - Обновить docstrings: YOLOv8n → RF-DETR
   - `_DEFAULT_MODEL` → `data/models/rf_detr_nano.onnx`

2. **`ml/gpu_server/server.py`** — заменить:
   - `YOLO_MODEL_PATH` → `RF_DETR_MODEL_PATH`
   - R2 key: `models/yolov8n.onnx` → `models/rf_detr_nano.onnx`
   - Startup check: обновить имя модели

3. **`ml/pyproject.toml`** — удалить `ultralytics>=8.0.0` из dependencies

4. **`data/models/models.manifest.json`** — добавить записи `rf_detr_nano` и `rf_detr_base`

5. **`ml/scripts/download_ml_models.py`** — добавить скачивание RF-DETR ONNX из HF

### Удаляемые

6. **`ml/yolov8n.pt`** — PyTorch веса YOLOv8n
7. **`ml/scripts/create_yolo_subset.py`** — создание YOLO-датасета
8. **`ml/scripts/train_yolo26_pose.py`** — обучение YOLO pose
9. **`ml/scripts/train_yolo26n_distill.py`** — дистилляция YOLO

### Новые файлы

10. **`ml/scripts/benchmark_detector.py`** — сравнение RF-DETR nano vs base vs YOLOv8n
11. **`ml/scripts/export_rf_detr.py`** — (опционально) самостоятельный экспорт ONNX из PyTorch

### Тесты

12. **`ml/tests/detection/test_person_detector.py`** — обновить docstrings (YOLOv8n → RF-DETR), логика тестов не меняется (API сохранён)

## Бенчмарк-стратегия

Скрипт `benchmark_detector.py` сравнивает:

| Метрика | Как измеряем |
|---------|-------------|
| FPS | `time.perf_counter()` на 100 кадров |
| Precision/Recall | Детекция person на skating видео с GT bboxes |
| Качество crop'а | Визуальная проверка: далеко/близко, вращения, отражения льда |
| Маленькие объекты | mAP на маленьких bboxes (далёкие фигуристы) |

Тестируемые модели:
- `rf_detr_nano.onnx` (~9M params)
- `rf_detr_base.onnx` (~29M params)

Выбор: по результатам бенчмарка. Если nano ≥ YOLOv8n — берём nano. Иначе base.

## Порядок миграции

1. Скачать RF-DETR ONNX веса (nano + base) из HF
2. Переписать `person_detector.py` (RF-DETR inference)
3. Обновить `gpu_server/server.py`
4. Удалить ultralytics из pyproject.toml
5. Удалить YOLO скрипты и веса
6. Обновить manifest + download script
7. Написать benchmark_detector.py
8. Запустить бенчмарк, выбрать модель
9. Обновить тесты
10. Проверить полный пайплайн: video → detect → pose → metrics

## Риски и митигация

| Риск | Митигация |
|------|-----------|
| RF-DETR хуже на маленьких объектах | Бенчмарк на skating видео; если nano хуже — попробовать base |
| Разный формат ONNX входа/выхода | Чистая переписка person_detector.py с полным покрытием тестами |
| Нет готовых ONNX на HF | Скрипт экспорта через `rfdetr` пакет |
| rfdetr PyPI конфликтует с существующими deps | rfdetr только в dev-deps (для экспорта), прод — чистый ONNX |
| Размер модели (29M vs 6.7M YOLOv8n) | nano ~9M сопоставим с YOLOv8n; base ~29M — только если nano недостаточно |

## IP-компоненты после миграции

| Компонент | Лицензия | Статус |
|-----------|----------|--------|
| RF-DETR веса (COCO) | Apache 2.0 | Чисто |
| RF-DETR код | Apache 2.0 | Не в проде (только ONNX) |
| PersonDetector код | Собственная | Чисто |
| ONNX Runtime | MIT | Чисто |
| ~~YOLOv8n веса~~ | ~~AGPL-3.0~~ | Удалено |
| ~~ultralytics Python~~ | ~~AGPL-3.0~~ | Удалено |