# OOFSkate Mobile Clone — Parallelization & Deep Analysis Report

> Дата: 2026-05-21
> Источник: 5 специализированных агентных исследований
> Спецификация: docs/specs/2026-05-21-oofskate-mobile-clone-design.md

## 1. Ключевые находки

### 1.1 Backend API — почти всё существует

Спецификация утверждала, что нужно добавить `GET /sessions`, `GET/PATCH /users/me`. **Это уже реализовано:**

| Endpoint | Статус | Файл |
|----------|--------|------|
| `GET /sessions` (paginated) | Существует | `backend/app/routes/sessions.py:98` |
| `GET /users/me` | Существует | `backend/app/routes/users.py:23` |
| `PATCH /users/me` | Существует (PATCH, не PUT) | `backend/app/routes/users.py:28` |

**Реальные gaps:**

| Что нужно | Почему |
|-----------|--------|
| Avatar upload (`POST /users/me/avatar`) | Нет endpoint для загрузки фото профиля |
| `angular_unit_preference` в настройках | Нет поля в `User` модели + `UpdateSettingsRequest` |
| Jump type classification | ML-классификатор не обучен (есть scaffold, нет модели) |
| Spin detection/classification | Не существует в коде |
| Under-rotation (четвертьоборота) | `compute_rotation_speed()` считает пиковую скорость, но не интегрирует в total rotation |

### 1.2 SSE Streaming — уже работает

`GET /process/{task_id}/stream` уже реализован (process.py:114). 5 событий: Starting → Dispatching → GPU complete → Preparing → Done. Мобильный клиент может потреблять SSE через Ktor напрямую.

**Ограничение**: Внутрипайплайновый прогресс (Detecting persons... → Extracting poses...) архитектурно заблокирован моделью Vast.ai Serverless — worker ждёт один HTTP-ответ от GPU сервера.

### 1.3 BLE — полностью параллелен

Phase 5 (BLE/IMU) **не блокирует** Phases 1-4. Камера, upload, auth, results — работают без BLE. BLE добавляется поверх через `NoOpBleRepository` как fallback.

### 1.4 KMP: критический путь 5 дней

```
setup(1d) → models(1d) → api(1d) → auth(1d) → state(1d)
```

Camera/BLE — чистый Android, параллелен с shared module.

---

## 2. Полный DAG параллелизации

```
WEEK 1 ──────────────────────────────────────────────────────────────────────

  TRACK A: Backend           TRACK B: KMP Shared          TRACK C: Android UI
  (Dev A)                    (Dev B)                      (Dev C)
  ─────────────              ─────────────                ─────────────
  Day 1: angular_unit        Day 1: build-logic/ +        Day 1: androidApp/
         preference +         libs.versions.toml +         scaffold, copy
         avatar upload          settings.gradle.kts         existing code
  Day 2: API tests            Day 2: models/ + util/       Day 2: migrate BLE,
                                                              camera, service
  Day 3: --                   Day 3: api/ (Ktor client)    Day 3: migrate UI
  Day 4: --                   Day 4: auth/ (JWT,           Day 4: wire :shared
                                    SecureStorage)              dependency
  Day 5: --                   Day 5: state/ (ViewModels)    Day 5: verify build

  TRACK D: ML Pipeline (parallel, no dependency on A/B/C)
  ─────────────
  Day 1-2: Under-rotation implementation (metrics.py)
  Day 3-5: Jump classifier training (needs labeled data)
  Day 5-7: Spin detection classifier


WEEK 2 ──────────────────────────────────────────────────────────────────────

  TRACK A: Backend           TRACK B: KMP Shared          TRACK C: Android UI
  ─────────────              ─────────────                ─────────────
  Day 1: New metric names     Day 1: shared module         Day 1: Auth screens
         in METRIC_REGISTRY +      tests                     (Login, Register)
         schemas                                              + mock API
  Day 2: Wire ML outputs      Day 2: Integration           Day 2: Camera screen
         into API responses       testing                      + upload flow
  Day 3: E2E backend test     Day 3: --                    Day 3: Session list +
                                                              detail screen

  TRACK D: ML Pipeline (continued)
  ─────────────
  Day 1-3: Spin classifier training
  Day 3-5: Wire into GPU server (Containerfile + model loading)


WEEK 3 ──────────────────────────────────────────────────────────────────────

  INTEGRATION WEEK (all tracks merge)
  ─────────────
  Day 1: Wire mobile upload → backend → ML pipeline → SSE → results display
  Day 2: Skeleton overlay (Compose Canvas, port from web SkeletonCanvas.tsx)
  Day 3: Offline resilience (WorkManager + Room), error handling, polish
```

### Визуализация параллелизма

```
Week 1:
  Dev A: ████████████ backend gaps (independent)
  Dev B: ██setup██models██api██auth██state
  Dev C: ██scaffold██migrate████████wire
  ML:    ████████████under-rotation██jump classifier

Week 2:
  Dev A: ████schema integration████E2E
  Dev B: ████████shared tests████
  Dev C: ██auth UI██camera+upload██results UI
  ML:    ████spin classifier████GPU wiring

Week 3:
  ALL:   ██E2E integration██skeleton overlay██offline+polish
```

---

## 3. Архитектурные решения (из исследований)

### 3.1 Gradle, не Amper

Amper 0.7.0 — preview, не поддерживает Hilt, KSP, protobuf. Gradle + convention plugins — стандарт для KMP проектов с Android.

### 3.2 Kable для BLE

Kable (JuulLabs) — coroutine-native KMP BLE библиотека. API маппится 1:1 на текущий BleManager:
- `Scanner.advertisements` → Flow<Advertisement>
- `peripheral.connect()` → suspend
- `peripheral.observe(characteristic)` → Flow<ByteArray> (WT901 0x61 frames)
- `peripheral.write(characteristic, data)` → suspend

Fallback: кастомный expect/actual с текущим BleManager.kt как Android actual.

### 3.3 Wt901Parser + Wt901Commander → commonMain

449 строк парсера + 167 строк командера — чистый Kotlin, нет Android-зависимостей (кроме `android.util.Log` и `java.util.Calendar`). Переносятся в shared module немедленно.

### 3.4 Mokkery, не MockK для commonTest

MockK — JVM-only, не компилируется в iosTest. Mokkery — KMP-native compiler plugin. MockK остаётся для androidUnitTest.

### 3.5 Under-rotation: реализация

Текущий `compute_rotation_speed()` считает пиковую угловую скорость через arctan2 + np.gradient. Для quarter-revolution точности нужно:

```python
def compute_total_rotation(shoulder_angles_unwrapped, fps):
    """Integrate unwrapped shoulder angle over flight phase."""
    total_degrees = abs(shoulder_angles_unwrapped[-1] - shoulder_angles_unwrapped[0])
    rotation_count = total_degrees / 360.0
    return total_degrees, rotation_count

def compute_under_rotation(measured_degrees, target_rotations):
    target_degrees = target_rotations * 360
    under_rotation = target_degrees - measured_degrees
    return under_rotation  # negative = over-rotated
```

Точность при 30fps: +/-45° на 3 rev/s. При 60fps: +/-22°. Quarter-revolution (90°) — детектируем на 60fps.

### 3.6 Offline-first upload

```
CameraX → File → Room (PendingUpload, status=READY)
  → WorkManager.enqueue(UploadWorker)

UploadWorker:
  1. POST /uploads/init → presigned URLs
  2. PUT parts concurrently (3) → ETags
  3. POST /uploads/complete
  4. POST /sessions (create session)
  5. POST /process (start ML)
  6. SSE listener → progress updates
  7. Room: status=COMPLETED
```

WorkManager переживает: background, kill, reboot. Room хранит upload_id + key для resume.

---

## 4. CI/CD параллелизация

### 5 параллельных цепочек на каждый push

```
  Python CI ───────────────────── py-lint → py-test → smoke
  Frontend CI ─────────────────── fe-lint → fe-typecheck → fe-test → fe-build
  Mobile lint ─────────────────── ktlintCheck
  KMP shared-test ─────────────── :shared:jvmTest + Kover
  Android unit-test ───────────── :app:testDebugUnitTest + Kover
                                    │
                                    v
                              build-release (gated)
```

Path-based triggers: `mobile/shared/**` → shared-test, `mobile/androidApp/**` → android-test, `mobile/build-logic/**` → both.

### Coverage: 3 Codecov флага

| Флаг | Инструмент | Модули |
|------|-----------|--------|
| `backend,ml` | pytest-cov | backend/ + ml/ |
| `frontend` | Vitest istanbul | frontend/ |
| `shared` | Kover | mobile/shared/ |
| `android` | Kover | mobile/androidApp/ |

---

## 5. Трекинг разработки (3 разработчика)

### Dev A: Backend + ML

| Неделя | Задачи |
|--------|--------|
| W1 | angular_unit_preference, avatar upload, under-rotation в metrics.py |
| W2 | Jump classifier training, schema интеграция, METRIC_REGISTRY |
| W3 | Spin classifier, GPU server wiring, E2E тестирование |

### Dev B: KMP Shared Module

| Неделя | Задачи |
|--------|--------|
| W1 | build-logic, version catalog, models, api, auth, state |
| W2 | shared tests, Wt901Parser/Commander port to commonMain |
| W3 | Integration testing, BLE expect/actual interfaces |

### Dev C: Android App

| Неделя | Задачи |
|--------|--------|
| W1 | androidApp scaffold, migrate BLE/camera/service, wire :shared |
| W2 | Auth screens, camera + upload, session list/detail |
| W3 | Skeleton overlay, offline resilience, polish |

### Конфликты: нулевые

- Dev A → `backend/`, `ml/` (не пересекается с mobile)
- Dev B → `mobile/shared/`, `mobile/build-logic/` (не пересекается с androidApp)
- Dev C → `mobile/androidApp/` (не пересекается с shared)

Единственный общий файл: `mobile/settings.gradle.kts` (настраивается Day 1, редко меняется).

---

## 6. Риски и неизвестные

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Jump classifier: нет размеченных данных | Высокая | Блокирует Phase 6 | Использовать synthetic data + rule-based fallback (rotations + toe_pick из element_defs.py) |
| Kable: WT901-специфичные баги | Средняя | Задержка Phase 5 | Fallback на кастомный expect/actual с текущим BleManager |
| SSE timeout на мобильных сетях | Низкая | Плохой UX при обработке | Увеличить SSE_STREAM_TIMEOUT + fallback polling GET /sessions/{id} |
| Under-rotation точность при 30fps | Средняя | +/-45° ошибка | Рекомендовать 60fps запись, sub-frame интерполяция |
| KMP/Native GC проблемы на iOS | Низкая (позже) | Задержка iOS порта | Мониторить, использовать стабильные паттерны |

---

## 7. Обновления к спецификации

Следующие изменения нужно внести в design spec:

1. **Backend API**: Удалить `GET /sessions` и `GET/PATCH /users/me` из "Нужно добавить" — уже существуют
2. **Добавить**: Avatar upload endpoint, angular_unit_preference setting
3. **ML**: Уточнить что jump classifier и spin detection требуют обучения (не только код)
4. **Under-rotation**: Добавить реализацию через cumulative angle integration
5. **BLE**: Указать Kable как основную библиотеку
6. **Testing**: Указать Mokkery для commonTest, Kover для coverage
7. **CI**: Заменить android.yml на mobile.yml с KMP shared-test
8. **Upload**: WorkManager + Room для offline-first
9. **Фазы**: Пересмотреть на основе 3-недельного плана параллельной разработки
