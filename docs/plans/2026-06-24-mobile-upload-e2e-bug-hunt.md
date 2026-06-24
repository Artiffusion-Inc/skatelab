# Mobile Upload E2E Bug-Hunt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Написать 5 Maestro E2E-флоу (U1–U5), которые гоняют upload-pipeline против реального backend `api.skatelab.ru` с эмуляцией обрывов сети и вокруг upload-состояния, чтобы выявлять НОВЫЕ (неизвестные) недоработки в mobile и backend; каждую найденную недоработку оформить issue с тегом для reviewer.

**Architecture:** Сквозные Maestro-флоу против живого backend через Docker-эмулятор `skatelab-emulator`. Multipart chunked upload в S3 (init → PUT parts → complete). Каждый сценарий ожидает корректное поведение и падает только при реальной недоработке. Production-код НЕ трогается (мандат: диагностика + тесты + issues).

**Tech Stack:** Maestro 2.6.x (в контейнере), Docker-эмулятор `budtmo/docker-android:emulator_14.0`, ADB, реальный backend `api.skatelab.ru`, тестовый аккаунт `test@skatelab.ru`/`Test123456`, asset `mobile/e2e/maestro/assets/test_video.mp4`.

## Global Constraints

- **Реальный backend** `api.skatelab.ru`, не fake. Multipart chunked upload в S3 (init → PUT parts concurrency=3 → complete).
- **Мандат:** только Maestro flows + partials + диагностика + issues. Никаких production-фиксов. Никаких правок `mobile/shared/`, `mobile/androidApp/src/main/`, `backend/app/`.
- **Тестовый аккаунт:** `test@skatelab.ru` / `Test123456` (`is_verified=true`, живой). Upload создаёт реальные sessions на prod-backend — одноразовые.
- **Maestro 2.6.x селекторы — по видимому тексту.** Селекторы из `upload-pipeline.yaml`: `"Upload video"`, `"00:12"` (длительность), `"axel"` (элемент), `"Uploading video…"`, `"Analysis complete"`. Login-pattern: `tapOn: "Email"` → `inputText` → `back` → ... → `tapOn: "Log in"`.
- **Airplane mode:** `setAirplaneMode: enabled/disabled` (из `upload-network-error.yaml`).
- **Retry/wait:** `retry: maxRetries: N` + `commands: [...]` (из `upload-pipeline.yaml`), `extendedWaitUntil: { visible, timeout }`.
- **Очистка состояния:** перед каждым flow `adb shell pm clear ru.skatelab.capture` + re-grant camera. Каждый flow логинится в начале (pattern `upload-pipeline.yaml` — единый session, избегает dADB-флакинга).
- **Asset:** `mobile/e2e/maestro/assets/test_video.mp4` (2.9MB). `addMedia: ["./assets/test_video.mp4"]` seeds gallery.
- **Mid-upload тайминг хрупок** — 3× прогона красных flow; устойчивый красный → баг, единичный → флакинг.
- **Worktree:** все коммиты в `worktree-auth-cache-logout-bug`. Никогда в master.

---

## File Structure

- Create: `mobile/e2e/maestro/flows/u1-mid-upload-airplane-resume.yaml`
- Create: `mobile/e2e/maestro/flows/u2-duplicate-upload.yaml`
- Create: `mobile/e2e/maestro/flows/u3-queue-airplane.yaml`
- Create: `mobile/e2e/maestro/flows/u4-airplane-before-upload-baseline.yaml`
- Create: `mobile/e2e/maestro/flows/u5-upload-rate-limit.yaml`
- Create: `mobile/e2e/UPLOAD_BUG_HUNT_INDEX.md` — индекс найденных багов/issues (обновляется в Task 7)
- Reuse: `mobile/e2e/maestro/partials/login_as.yaml` (создан в подходе A)
- Reuse: `mobile/e2e/maestro/partials/pick_first_video.yaml` (существует)
- Reuse: `mobile/e2e/maestro/assets/test_video.mp4` (существует)

Каждый flow-файл — один сценарий, один responsibility, независимо запускается.

---

### Task 1: UPLOAD_BUG_HUNT_INDEX.md preconditions + partials check

**Files:**
- Create: `mobile/e2e/UPLOAD_BUG_HUNT_INDEX.md`
- Verify: `mobile/e2e/maestro/partials/login_as.yaml` + `pick_first_video.yaml` exist

**Interfaces:**
- Consumes: аккаунт A, существующие partials, asset
- Produces: индекс с preconditions (используют Tasks 2–6)

- [ ] **Step 1: Проверить preconditions существуют**

```bash
ls mobile/e2e/maestro/partials/login_as.yaml mobile/e2e/maestro/partials/pick_first_video.yaml mobile/e2e/maestro/assets/test_video.mp4
```
Expected: все три файла существуют (login_as из подхода A, pick_first_video + test_video — существующие).

- [ ] **Step 2: Написать UPLOAD_BUG_HUNT_INDEX.md preconditions**

```markdown
# E2E Bug-Hunt Index — upload on network breaks

Bug-hunt E2E-набор гоняет upload-pipeline против реального backend `api.skatelab.ru` с эмуляцией обрывов сети и вокруг upload-состояния, чтобы выявлять новые недоработки в mobile (ChunkedUploader/UploadWorker/queue) и backend (uploads.py). Каждую найденную недоработку → issue с тегом. Production-код не трогается (мандат: диагностика + тесты + issues).

## Preconditions

- **Backend:** `https://api.skatelab.ru/v1/` (реальный, живой)
- **Аккаунт:** `test@skatelab.ru` / `Test123456` (`is_verified=true`)
- **Эмулятор:** `skatelab-emulator` (budtmo/docker-android:emulator_14.0), Maestro 2.6.x в контейнере
- **APK:** debug-сборка с `API_BASE_URL=https://api.skatelab.ru/v1/`
- **Asset:** `mobile/e2e/maestro/assets/test_video.mp4` (2.9MB)
- **Partials:** `login_as.yaml` (подход A), `pick_first_video.yaml` (существующий)

## Scenarios

| Flow | Сценарий | Статус | Issue | Примечание |
|------|----------|--------|-------|------------|
| u4-airplane-before-upload-baseline | airplane до upload → retry → complete (baseline) | TBD | — | — |
| u1-mid-upload-airplane-resume | airplane mid-upload → resume → complete | TBD | — | — |
| u2-duplicate-upload | duplicate upload того же видео | TBD | — | — |
| u3-queue-airplane | queue с pending + обрыв | TBD | — | — |
| u5-upload-rate-limit | rate-limit edge (последний — pollutes counter) | TBD | — | — |

## Triage legend

- **PASS** — поверхность здорова
- **FAIL** — устойчивый красный (3/3) → баг, открыт issue
- **FLAKY** — единичный красный → не баг
- **SKIP** — пропуск с причиной

Порядок прогона: U4 (baseline) → U1 → U2 → U3 → U5 (последним — загрязняет rate-limit счётчик `upload:init`).
```

- [ ] **Step 3: Commit**

```bash
git add mobile/e2e/UPLOAD_BUG_HUNT_INDEX.md
git commit -m "test(mobile-e2e): upload bug-hunt index + preconditions"
```

---

### Task 2: U4 — airplane до upload → retry → complete (baseline)

**Files:**
- Create: `mobile/e2e/maestro/flows/u4-airplane-before-upload-baseline.yaml`

**Interfaces:**
- Consumes: аккаунт A, asset, partials
- Produces: контрольный GREEN-сценарий (если падает — инфра/базовый retry сломан)

- [ ] **Step 1: Написать flow**

```yaml
appId: ru.skatelab.capture
tags:
  - bug-hunt
  - upload
---
# U4 baseline: airplane ON before launch → upload attempt → "No connection"/"Retry" → airplane OFF → retry → complete.
# Control GREEN: confirms pre-upload retry path healthy. If RED = infra/basic retry broken.
- setAirplaneMode: enabled
- addMedia: ["./assets/test_video.mp4"]
- launchApp
# Login (inline — Maestro setAirplaneMode before launch means fresh session)
- runFlow:
    when:
      visible: "While using the app"
    commands:
      - tapOn: "While using the app"
- assertVisible: "Log in to your account"
- tapOn: "Email"
- inputText: test@skatelab.ru
- back
- tapOn: "Password"
- inputText: Test123456
- back
- tapOn: "Log in"
- assertVisible: "Camera"
# Attempt upload while offline
- tapOn: "Upload video"
- runFlow: ../partials/pick_first_video.yaml
- assertVisible: "No connection"
- assertVisible: "Retry"
# Restore network and retry
- setAirplaneMode: disabled
- tapOn: "Retry"
# Wait for processing to complete (network restored)
- retry:
    maxRetries: 30
    commands:
      - assertVisible: "Analysis complete"
```

- [ ] **Step 2: Прогнать flow (см. Task 7 для run-процесса)**

```bash
docker exec skatelab-emulator adb shell pm clear ru.skatelab.capture
docker exec skatelab-emulator adb shell pm grant ru.skatelab.capture android.permission.CAMERA
docker cp mobile/e2e/maestro/flows/. skatelab-emulator:/home/androidusr/flows/
docker cp mobile/e2e/maestro/partials/. skatelab-emulator:/home/androidusr/partials/
docker cp mobile/e2e/maestro/assets/. skatelab-emulator:/home/androidusr/assets/
docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
  maestro test --device emulator-5554 /home/androidusr/flows/u4-airplane-before-upload-baseline.yaml
```
Expected: PASS. Если FAIL — инфра-проблема (эмулятор/backend/APK/asset), не баг продукта; чинить окружение.

- [ ] **Step 3: Commit**

```bash
git add mobile/e2e/maestro/flows/u4-airplane-before-upload-baseline.yaml
git commit -m "test(mobile-e2e): U4 airplane-before-upload baseline flow"
```

---

### Task 3: U1 — airplane mid-upload → resume → complete

**Files:**
- Create: `mobile/e2e/maestro/flows/u1-mid-upload-airplane-resume.yaml`

**Interfaces:**
- Consumes: аккаунт A, asset, partials
- Produces: bug-hunt flow — ищет resume после mid-upload обрыва

- [ ] **Step 1: Написать flow**

```yaml
appId: ru.skatelab.capture
tags:
  - bug-hunt
  - upload
---
# U1: upload starts → airplane ON mid-upload (~2s after "Uploading video…") → wait → airplane OFF → resume → complete.
# Bug-hunt: expects upload resumes (reuses uploadId, not restart) after mid-upload break. RED = hang/restart/broken complete.
- addMedia: ["./assets/test_video.mp4"]
- launchApp
- runFlow:
    when:
      visible: "While using the app"
    commands:
      - tapOn: "While using the app"
- runFlow:
    when:
      visible: "Camera"
    commands:
      - tapOn: "Profile"
      - scroll
      - scroll
      - tapOn: "Log out"
      - assertVisible: "Log in to your account"
- assertVisible: "Log in to your account"
- tapOn: "Email"
- inputText: test@skatelab.ru
- back
- tapOn: "Password"
- inputText: Test123456
- back
- tapOn: "Log in"
- assertVisible: "Camera"
# Start upload
- tapOn: "Upload video"
- tapOn: "00:12"
- assertVisible: "axel"
- tapOn: "axel"
- assertVisible: "Uploading video…"
# Break mid-upload: airplane ON shortly after upload starts
- setAirplaneMode: enabled
- extendedWaitUntil:
    visible: "Retry"
    timeout: 15000
- setAirplaneMode: disabled
# Retry / resume — upload must resume (not restart from scratch)
- tapOn: "Retry"
- retry:
    maxRetries: 40
    commands:
      - assertVisible: "Analysis complete"
```

- [ ] **Step 2: Прогнать 3× (отсев флакинга mid-upload тайминга)**

```bash
docker exec skatelab-emulator adb shell pm clear ru.skatelab.capture
docker exec skatelab-emulator adb shell pm grant ru.skatelab.capture android.permission.CAMERA
docker cp mobile/e2e/maestro/flows/. skatelab-emulator:/home/androidusr/flows/
docker cp mobile/e2e/maestro/partials/. skatelab-emulator:/home/androidusr/partials/
docker cp mobile/e2e/maestro/assets/. skatelab-emulator:/home/androidusr/assets/
# Повторить 3 раза:
docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
  maestro test --device emulator-5554 /home/androidusr/flows/u1-mid-upload-airplane-resume.yaml
```
Expected: PASS (resume здоров) ИЛИ устойчивый FAIL (3/3) → баг (Task 7 диагностика). Единичный FAIL → флакинг.

- [ ] **Step 3: Commit**

```bash
git add mobile/e2e/maestro/flows/u1-mid-upload-airplane-resume.yaml
git commit -m "test(mobile-e2e): U1 mid-upload airplane resume bug-hunt flow"
```

---

### Task 4: U2 — duplicate upload того же видео

**Files:**
- Create: `mobile/e2e/maestro/flows/u2-duplicate-upload.yaml`

**Interfaces:**
- Consumes: аккаунт A, asset (seeded once), partials
- Produces: bug-hunt flow — ищет битую session / дубликат / конфликт при повторном upload

- [ ] **Step 1: Написать flow**

```yaml
appId: ru.skatelab.capture
tags:
  - bug-hunt
  - upload
---
# U2: complete upload → re-upload the same video → expect second session or meaningful duplicate handling.
# Bug-hunt: re-upload same file must not create broken session / multipart conflict / silent duplicate.
- addMedia: ["./assets/test_video.mp4"]
- launchApp
- runFlow:
    when:
      visible: "While using the app"
    commands:
      - tapOn: "While using the app"
- runFlow:
    when:
      visible: "Camera"
    commands:
      - tapOn: "Profile"
      - scroll
      - scroll
      - tapOn: "Log out"
      - assertVisible: "Log in to your account"
- assertVisible: "Log in to your account"
- tapOn: "Email"
- inputText: test@skatelab.ru
- back
- tapOn: "Password"
- inputText: Test123456
- back
- tapOn: "Log in"
- assertVisible: "Camera"
# First upload — complete
- tapOn: "Upload video"
- tapOn: "00:12"
- assertVisible: "axel"
- tapOn: "axel"
- assertVisible: "Uploading video…"
- retry:
    maxRetries: 30
    commands:
      - assertVisible: "Analysis complete"
# Re-upload the same video (asset already seeded in gallery)
- tapOn: "Upload video"
- tapOn: "00:12"
- assertVisible: "axel"
- tapOn: "axel"
- assertVisible: "Uploading video…"
- retry:
    maxRetries: 30
    commands:
      - assertVisible: "Analysis complete"
```

- [ ] **Step 2: Прогнать**

```bash
docker exec skatelab-emulator adb shell pm clear ru.skatelab.capture
docker exec skatelab-emulator adb shell pm grant ru.skatelab.capture android.permission.CAMERA
docker cp mobile/e2e/maestro/flows/. skatelab-emulator:/home/androidusr/flows/
docker cp mobile/e2e/maestro/partials/. skatelab-emulator:/home/androidusr/partials/
docker cp mobile/e2e/maestro/assets/. skatelab-emulator:/home/androidusr/assets/
docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
  maestro test --device emulator-5554 /home/androidusr/flows/u2-duplicate-upload.yaml
```
Expected: PASS (второй upload проходит корректно) ИЛИ FAIL → баг (Task 7).

- [ ] **Step 3: Commit**

```bash
git add mobile/e2e/maestro/flows/u2-duplicate-upload.yaml
git commit -m "test(mobile-e2e): U2 duplicate upload bug-hunt flow"
```

---

### Task 5: U3 — queue с pending + обрыв

**Files:**
- Create: `mobile/e2e/maestro/flows/u3-queue-airplane.yaml`

**Interfaces:**
- Consumes: аккаунт A, asset (seeded twice), partials
- Produces: bug-hunt flow — ищет потерю queue-состояния / WorkManager collision при обрыве

- [ ] **Step 1: Написать flow**

```yaml
appId: ru.skatelab.capture
tags:
  - bug-hunt
  - upload
---
# U3: seed 2 videos → start first upload → airplane ON mid-upload → start second (queues) → airplane OFF → both complete.
# Bug-hunt: queue must process both sequentially after break, no loss/duplicate/WorkManager collision.
- addMedia: ["./assets/test_video.mp4", "./assets/test_video.mp4"]
- launchApp
- runFlow:
    when:
      visible: "While using the app"
    commands:
      - tapOn: "While using the app"
- runFlow:
    when:
      visible: "Camera"
    commands:
      - tapOn: "Profile"
      - scroll
      - scroll
      - tapOn: "Log out"
      - assertVisible: "Log in to your account"
- assertVisible: "Log in to your account"
- tapOn: "Email"
- inputText: test@skatelab.ru
- back
- tapOn: "Password"
- inputText: Test123456
- back
- tapOn: "Log in"
- assertVisible: "Camera"
# First upload
- tapOn: "Upload video"
- tapOn: "00:12"
- assertVisible: "axel"
- tapOn: "axel"
- assertVisible: "Uploading video…"
# Break mid-upload
- setAirplaneMode: enabled
- extendedWaitUntil:
    visible: "Retry"
    timeout: 15000
# Queue second while offline
- tapOn: "Upload video"
- runFlow: ../partials/pick_first_video.yaml
# Restore network — both must complete
- setAirplaneMode: disabled
- tapOn: "Retry"
- retry:
    maxRetries: 60
    commands:
      - assertVisible: "Analysis complete"
```

- [ ] **Step 2: Прогнать 3×**

```bash
docker exec skatelab-emulator adb shell pm clear ru.skatelab.capture
docker exec skatelab-emulator adb shell pm grant ru.skatelab.capture android.permission.CAMERA
docker cp mobile/e2e/maestro/flows/. skatelab-emulator:/home/androidusr/flows/
docker cp mobile/e2e/maestro/partials/. skatelab-emulator:/home/androidusr/partials/
docker cp mobile/e2e/maestro/assets/. skatelab-emulator:/home/androidusr/assets/
docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
  maestro test --device emulator-5554 /home/androidusr/flows/u3-queue-airplane.yaml
```

- [ ] **Step 3: Commit**

```bash
git add mobile/e2e/maestro/flows/u3-queue-airplane.yaml
git commit -m "test(mobile-e2e): U3 queue+airplane bug-hunt flow"
```

---

### Task 6: U5 — rate-limit edge на upload-init

**Files:**
- Create: `mobile/e2e/maestro/flows/u5-upload-rate-limit.yaml`

**Interfaces:**
- Consumes: аккаунт A, asset, partials
- Produces: bug-hunt flow — ищет некорректную обработку backend rate-limit (`upload:init: max 10/60s`) mobile

- [ ] **Step 1: Написать flow**

```yaml
appId: ru.skatelab.capture
tags:
  - bug-hunt
  - upload
---
# U5: rapid upload-init attempts (airplane ON right after init to trigger retry/init cycle) → expect rate-limit handled (no crash/hang).
# Bug-hunt: backend rate-limit (upload:init max 10/60s) must surface in mobile as AppError/UX, not crash/silent.
# NOTE: pollutes rate-limit counter for test@skatelab.ru — run LAST in suite.
- addMedia: ["./assets/test_video.mp4"]
- launchApp
- runFlow:
    when:
      visible: "While using the app"
    commands:
      - tapOn: "While using the app"
- runFlow:
    when:
      visible: "Camera"
    commands:
      - tapOn: "Profile"
      - scroll
      - scroll
      - tapOn: "Log out"
      - assertVisible: "Log in to your account"
- assertVisible: "Log in to your account"
- tapOn: "Email"
- inputText: test@skatelab.ru
- back
- tapOn: "Password"
- inputText: Test123456
- back
- tapOn: "Log in"
- assertVisible: "Camera"
# Repeatedly attempt upload with airplane toggling to force init retries (triggers rate-limit after 10)
- repeat:
    times: 12
    commands:
      - setAirplaneMode: enabled
      - tapOn: "Upload video"
      - runFlow: ../partials/pick_first_video.yaml
      - extendedWaitUntil:
          visible: "Retry"
          timeout: 5000
      - setAirplaneMode: disabled
      - tapOn: "Retry"
      - extendedWaitUntil:
          visible: "Camera"
          timeout: 10000
# After rate-limit: app must still be responsive (no crash/hang)
- assertVisible: "Camera"
```

- [ ] **Step 2: Прогнать (последним — загрязняет rate-limit)**

```bash
docker exec skatelab-emulator adb shell pm clear ru.skatelab.capture
docker exec skatelab-emulator adb shell pm grant ru.skatelab.capture android.permission.CAMERA
docker cp mobile/e2e/maestro/flows/. skatelab-emulator:/home/androidusr/flows/
docker cp mobile/e2e/maestro/partials/. skatelab-emulator:/home/androidusr/partials/
docker cp mobile/e2e/maestro/assets/. skatelab-emulator:/home/androidusr/assets/
docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
  maestro test --device emulator-5554 /home/androidusr/flows/u5-upload-rate-limit.yaml
```
Expected: PASS (Camera visible, no crash) ИЛИ FAIL → баг. Собрать `adb logcat` для проверки AppError-маппинга rate-limit.

- [ ] **Step 3: Commit**

```bash
git add mobile/e2e/maestro/flows/u5-upload-rate-limit.yaml
git commit -m "test(mobile-e2e): U5 upload rate-limit edge flow"
```

---

### Task 7: Прогнать suite, triage, открыть issues, обновить индекс и PR

**Files:**
- Modify: `mobile/e2e/UPLOAD_BUG_HUNT_INDEX.md` — заполнить статусы + issue-ссылки

**Interfaces:**
- Consumes: все flows (Tasks 2–6), аккаунт A
- Produces: issue-индекс для reviewer + открытые issues + обновлённый PR #325 body

- [ ] **Step 1: Убедиться, что debug APK установлен в эмуляторе**

```bash
# Если APK уже установлен (из подхода A) — переустановить не нужно. Проверить:
docker exec skatelab-emulator adb shell pm list packages | grep ru.skatelab.capture
# Если нет — собрать и установить (см. подход A Task 10 Step 1–2):
# docker cp /tmp/skatelab-apk-out/androidApp-debug.apk skatelab-emulator:/tmp/app-debug.apk
# docker exec skatelab-emulator adb install /tmp/app-debug.apk
```

- [ ] **Step 2: Скопировать flows + partials + assets в контейнер**

```bash
docker cp mobile/e2e/maestro/flows/. skatelab-emulator:/home/androidusr/flows/
docker cp mobile/e2e/maestro/partials/. skatelab-emulator:/home/androidusr/partials/
docker cp mobile/e2e/maestro/assets/. skatelab-emulator:/home/androidusr/assets/
```

- [ ] **Step 3: Прогнать suite по порядку**

```bash
# Порядок: U4 (baseline) → U1 → U2 → U3 → U5 (последним — загрязняет rate-limit)
for f in u4-airplane-before-upload-baseline u1-mid-upload-airplane-resume u2-duplicate-upload u3-queue-airplane u5-upload-rate-limit; do
  docker exec skatelab-emulator adb shell pm clear ru.skatelab.capture
  docker exec skatelab-emulator adb shell pm grant ru.skatelab.capture android.permission.CAMERA
  echo "=== $f ==="
  docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
    maestro test --device emulator-5554 /home/androidusr/flows/$f.yaml 2>&1 | tail -15
done
```

- [ ] **Step 4: Для каждого красного flow — прогнать 3× и собрать диагностику**

```bash
# Для красного flow (пример u1):
docker exec skatelab-emulator adb shell pm clear ru.skatelab.capture
docker exec skatelab-emulator adb shell pm grant ru.skatelab.capture android.permission.CAMERA
docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator \
  maestro test --device emulator-5554 /home/androidusr/flows/u1-mid-upload-airplane-resume.yaml
# Повторить 3×. Устойчивый красный → баг. Собрать:
docker exec skatelab-emulator adb logcat -d -t 800 | grep -iE 'skatelab|Upload|Chunked|S3|multipart|Worker|Exception|http' > /tmp/$f-logcat.txt
# Backend logs (если доступ) — grep по upload/init/complete/events
```

- [ ] **Step 5: Для каждого устойчивого красного — определить поверхность root cause**

Прочитать trace по коду:
- Upload зависает/рестарт после airplane → `ChunkedUploader.kt` (resume логика, uploadId reuse) + `UploadWorker.kt` (`Result.retry()`, `incrementRetry`) → поверхность mobile.
- `complete` падает с missing parts → multipart-состояние потеряно → mobile (ChunkedUploader не хранит uploaded parts) ИЛИ backend (`complete` проверяет parts).
- Duplicate → битая session → mobile (`UploadScheduler`/dedup) ИЛИ backend (sessions create / multipart conflict).
- Queue потеря → `UploadWorker`/`UploadScheduler` WorkManager collision → mobile.
- Rate-limit crash → `ExceptionMapping`/`AppError` + backend `upload:init` response → mobile AppError-маппинг.
- Определить тег: `bug` + `testing/repro` (метки `mobile`/`backend` в репо нет — описать поверхность в body).

- [ ] **Step 6: Открыть issue для каждого найденного бага**

```bash
gh issue create -R Artiffusion-Inc/skatelab --title "..." --label "bug,testing/repro" --body "$(cat <<'EOF'
## What
...

## Repro
Flow: mobile/e2e/maestro/flows/u1-mid-upload-airplane-resume.yaml (worktree worktree-auth-cache-logout-bug, коммит <SHA>)
Preconditions: аккаунт test@skatelab.ru, asset test_video.mp4, эмулятор skatelab-emulator.

## Ожидаемое vs фактическое
...

## Гипотеза root cause (file:line)
...

## Impact для prod
...

## Proposed fix (отдельным PR)
...

## Связано
- Спека: docs/specs/2026-06-24-mobile-upload-e2e-bug-hunt-design.md
EOF
)"
```

- [ ] **Step 7: Обновить UPLOAD_BUG_HUNT_INDEX.md — статусы + issue-номера**

Заполнить таблицу: PASS/FAIL/FLAKY/SKIP + issue # для каждого flow. Зелёные → "PASS — surface healthy"; красные устойчивые → "FAIL — issue #NNN"; единичные → "FLAKY — not a bug".

- [ ] **Step 8: Commit индекс**

```bash
git add mobile/e2e/UPLOAD_BUG_HUNT_INDEX.md
git commit -m "test(mobile-e2e): upload bug-hunt triage results + issue index"
```

- [ ] **Step 9: Обновить PR #325 body с upload bug-hunt секцией**

Добавить секцию (по аналогии с E2E session bug-hunt секцией): triage-таблица U1–U5, найденные недоработки со ссылками на issues, ссылки на спеку/план/индекс. Через `gh pr edit 325 -R Artiffusion-Inc/skatelab --body-file <file>` (аккуратно, вставка перед codesmith-footer — см. подход A Task 10).

- [ ] **Step 10: Push в PR #325**

```bash
git push origin worktree-auth-cache-logout-bug
```

---

## Self-Review (выполнено автором)

- **Spec coverage:** U1–U5 → Tasks 3,4,5,2,6. Task 1 = preconditions, Task 7 = triage+issues+PR. Все 5 сценариев + preconditions + issue-форма покрыты.
- **Placeholder scan:** Реальные селекторы из `upload-pipeline.yaml` ( `"00:12"`, `"axel"`, `"Uploading video…"`, `"Analysis complete"` ). Плейсхолдеров/TBD нет.
- **Type consistency:** Partial `login_as.yaml` не используется в upload flows (inline login, по pattern `upload-pipeline.yaml` который логинится inline — для единообразия с существующими upload-флоу). Имена flow-файлов совпадают в Tasks и Step 3 suite-цикла.
- **Мандат соблюдён:** все задачи — только flows/partials/диагностика/issues. Никаких правок production-кода.