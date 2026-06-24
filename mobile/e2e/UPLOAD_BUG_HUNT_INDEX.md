# E2E Bug-Hunt Index — upload on network breaks

Bug-hunt E2E-набор гоняет upload-pipeline против реального backend `api.skatelab.ru` с эмуляцией обрывов сети и вокруг upload-состояния, чтобы выявлять новые недоработки в mobile (`ChunkedUploader`/`UploadWorker`/queue) и backend (`uploads.py`). Каждую найденную недоработку → issue с тегом. Production-код не трогается (мандат: диагностика + тесты + issues).

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