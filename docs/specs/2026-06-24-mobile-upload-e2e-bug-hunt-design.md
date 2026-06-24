# E2E Bug-Hunt: upload на обрывах сети против реального backend

**Дата:** 2026-06-24
**Статус:** Approved
**Worktree:** `worktree-auth-cache-logout-bug`
**Мандат:** диагностика + тесты + issues. Никаких production-фиксов в этой работе.
**Связано:** продолжение `2026-06-24-mobile-session-e2e-bug-hunt-design.md` (подход A — цикл сессии). Этот спека — подход B — upload-поверхность.

## Назначение

Набор Maestro E2E-флоу, которые гоняют **upload-pipeline против реального backend** `api.skatelab.ru` с эмуляцией обрывов сети и вокруг upload-состояния, чтобы **выявлять новые (неизвестные) недоработки** в mobile (`ChunkedUploader`/`UploadWorker`/`UploadQueueViewModel`) и backend (`uploads.py` init/complete/presign + rate-limit). Каждая найденная недоработка → issue с тегом для reviewer.

**Принцип поиска новых багов:** каждый сценарий ожидает корректное поведение и падает только при реальной недоработке. Зелёный → поверхность здорова; красный (устойчивый) → новый баг → issue.

## Принципы ограничений

- **Реальный backend** `api.skatelab.ru`, не fake. Multipart chunked upload в S3 (init → PUT parts concurrency=3 → complete).
- **Scope = сеть + состояние:** airplane mode до/mid-upload, восстановление сети → resume/complete, duplicate upload того же видео, queue с несколькими pending + обрыв. (Processing-pipeline — отдельная поверхность, не здесь.)
- **Мандат:** только Maestro flows + partials + диагностика + issues. Никаких правок production-кода.
- **Тестовый аккаунт:** `test@skatelab.ru` / `Test123456` (is_verified=true). Upload создаёт реальные sessions на prod-backend — помечать как одноразовые (видео-asset `test_video.mp4`, детерминированные названия).
- **Maestro 2.6.x:** селекторы по видимому тексту. `addMedia` seeding gallery + `pick_first_video` partial — переиспользуем.
- **Mid-upload тайминг хрупок** — airplane через N сек после `assertVisible: "Uploading video…"`. Сценарии mid-upload прогонять 3×; устойчивый красный → баг, единичный → флакинг.

## Upload-поверхность (для reviewer-контекста)

- Mobile: `mobile/androidApp/src/main/java/ru/skatelab/capture/upload/ChunkedUploader.kt` (multipart, concurrency=3), `UploadWorker.kt` (WorkManager `Result.retry()` + `incrementRetry`), `UploadScheduler.kt`, `UploadQueueViewModel/Screen.kt` (queue UI, "Retry", "No connection").
- Backend: `backend/app/routes/uploads.py` — `@post("/init")` (presigned URLs + uploadId + chunkSize), `@post("/complete")` (complete_multipart), `@post("/presign")` (small files). Rate-limit `upload:init/complete/presign: max 10/60s`.
- Существующий flow `upload-network-error.yaml` — airplane **до** upload ("No connection" + "Retry"). Подход B расширяет: mid-upload, resume, duplicate, queue.

## Сценарии

Каждый — отдельный Maestro flow в `mobile/e2e/maestro/flows/`. Префикс `u` (upload). Все начинаются с login (по pattern `upload-pipeline.yaml`) — единый session, чтобы избежать dADB-флакинга от повторных launch.

### U1. Airplane mid-upload → resume → complete (`u1-mid-upload-airplane-resume.yaml`)
login → addMedia → "Upload video" → выбор клипа/элемента → `assertVisible: "Uploading video…"` → **airplane ON через ~2 сек** → ждать → airplane OFF → ожидать: upload **возобновляется** (resume переиспользует uploadId, не начинает заново) → `assertVisible: "Analysis complete"`.
**Ищет:** resume после mid-upload обрыва не работает — upload зависает, начинается заново (дублирующий multipart), или `complete` падает с missing parts.

### U2. Duplicate upload того же видео (`u2-duplicate-upload.yaml`)
login → addMedia → полный upload до `"Analysis complete"` → **повторный** upload того же видео (addMedia уже seeded) → ожидать: либо корректная вторая session, либо осмысленное "уже загружено"/дубликат-detected. Не падать молча, не дублировать multipart-состояние на backend.
**Ищет:** повторный upload того же файла создаёт **битую** session / конфликт multipart / дубликат-данные без предупреждения.

### U3. Queue с несколькими pending + обрыв (`u3-queue-airplane.yaml`)
login → addMedia **дважды** (или несколько видео) → старт upload первого → airplane ON mid-upload → старт второго (queue) → airplane OFF → ожидать: queue обрабатывает оба последовательно, оба complete, без потери/дублирования.
**Ищет:** queue-состояние теряется при обрыве, второй upload не стартует после первого, или WorkManager-collision.

### U4. Airplane до upload → retry → complete (расширение существующего, baseline) (`u4-airplane-before-upload-baseline.yaml`)
airplane ON (до launch) → launch → "Upload video" → "No connection" + "Retry" → airplane OFF → tap "Retry" → ожидать: upload проходит после retry → "Analysis complete".
**Контрольный:** подтверждает, что retry-path (до старта upload) здоров. Если падает — инфра/базовый retry сломан.

### U5. Rate-limit edge на upload-init (`u5-upload-rate-limit.yaml`)
login → запуск upload-init 11+ раз подряд (airplane ON сразу после init, или rapid tap upload → cancel → upload) → ожидать: backend rate-limit (`upload:init: max 10/60s`) корректно обрабатывается mobile (AppError/UX, не краш/зависание).
**Ищет:** rate-limit backend не surfaced в mobile — silent fail / краш / дублирующие запросы. Прогонять последним (загрязняет rate-limit счётчик).

## Test doubles и preconditions

- **Asset:** `mobile/e2e/maestro/assets/test_video.mp4` (2.9MB, существует). `addMedia` seeds в gallery эмулятора.
- **Partial:** переиспользуем `partials/pick_first_video.yaml` и `partials/login_as.yaml` (создан в подходе A).
- **Airplane mode:** Maestro `setAirplaneMode: enabled/disabled` (используется в существующем `upload-network-error.yaml`).
- **Очистка:** перед каждым flow `adb shell pm clear` + re-grant camera (как в подходе A), кроме U1/U3 где нужен сохранённый login mid-flow (launch с уже залогиненным состоянием — pattern `upload-pipeline.yaml` логинится в начале каждого flow).
- **Sessions накапливаются** на prod-backend для `test@skatelab.ru` — пометить одноразовые, не чистить (prod-data).

## Поток выполнения и верификация

1. Написать 5 Maestro flows (U1–U5) + при необходимости partials.
2. Прогнать локально через `maestro test --device emulator-5554 <flow>` (по pattern подхода A).
3. Для каждого красного flow — прогнать 3× (отсев Maestro-флакинга mid-upload тайминга).
4. Устойчивый красный → диагностика: `adb logcat` (UploadWorker/ChunkedUploader/S3 errors) + backend logs + trace по коду → определить поверхность (mobile/backend) → открыть issue (`bug` + `testing/repro`).
5. Единичный красный → флакинг (логируем).
6. Зелёный → поверхность здорова.
7. Issue-индекс в `mobile/e2e/UPLOAD_BUG_HUNT_INDEX.md` + обновить PR #325 body.
8. **Никаких production-фиксов.** PR содержит только flows + partials + индекс.

## Scope

- 5 Maestro flows (U1–U5) + partials (переиспользуются).
- Прогон против реального backend.
- Issues на найденные баги (mobile/backend), обновление `UPLOAD_BUG_HUNT_INDEX.md` + PR #325 body.

## Non-goals

- Production-фиксы (отдельные PR по issues).
- Processing-pipeline surface (upload → process → results) — отдельная работа.
- Frontend-тесты (отдельная поверхность).
- CI-интеграция E2E.
- S3/RustFS внутренняя диагностика (только через backend-логи).

## Риски

- **Mid-upload тайминг хрупок** (U1/U3) — airplane в произвольный момент multipart-цикла недетерминирован. Mitigation: 3× прогоны, устойчивый красный → баг.
- **Airplane mode на эмуляторе** может не полностью эмулировать TCP-обрыв (зависит от emulator network stack) — проверено в существующем `upload-network-error.yaml` что работает.
- **Sessions накапливаются** на prod-backend — U2/U3 создают несколько sessions за прогон. Принять как test-fixture, не чистить (одноразовые).
- **U5 rate-limit загрязняет** счётчик `upload:init` для `test@skatelab.ru` — прогонять последним.
- **Multipart uploadId orphaning** — если U1/U3 оставят незавершённые multipart на S3, это storage-мусор на prod. Помечать в issue если найдено (backend cleanup — отдельная работа).

## Связанные артефакты

- `docs/specs/2026-06-24-mobile-session-e2e-bug-hunt-design.md` — подход A (цикл сессии).
- `mobile/e2e/maestro/flows/upload-pipeline.yaml` — happy-path upload (селекторы).
- `mobile/e2e/maestro/flows/upload-network-error.yaml` — airplane до upload (U4 базируется на нём).
- Memory `local-e2e-setup` — Docker-эмулятор + Maestro, реальный backend E2E рабочий.