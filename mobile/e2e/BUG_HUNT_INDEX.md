# E2E Bug-Hunt Index — session lifecycle

Bug-hunt E2E-набор гоняет полный цикл пользовательской сессии против реального backend `api.skatelab.ru`, чтобы выявлять **новые** (неизвестные) недоработки в mobile и backend. Каждую найденную недоработку → issue с тегом для reviewer. Production-код не трогается (мандат: диагностика + тесты + issues).

## Preconditions

- **Backend:** `https://api.skatelab.ru/v1/` (реальный, живой)
- **Аккаунт A:** `test@skatelab.ru` / `Test123456` (`is_verified=true`)
- **Аккаунт B:** `e2e2@skatelab.ru` / `Test123456` (`is_verified=true`, создан 2026-06-24 через `/auth/register` + `UPDATE users SET is_verified=true` в prod-DB `infra-postgres-1` — test-fixture setup)
- **Эмулятор:** `skatelab-emulator` (budtmo/docker-android:emulator_14.0), Maestro 2.6.x в контейнере
- **APK:** debug-сборка с `API_BASE_URL=https://api.skatelab.ru/v1/`

## Scenarios

| Flow | Сценарий | Статус | Issue |
|------|----------|--------|-------|
| s5-relogin-same-baseline | re-login same account (baseline) | TBD | — |
| s1-cross-account-switch | cross-account switch (A→B) | TBD | — |
| s3-read-after-logout | read after logout (UI state leak) | TBD | — |
| s4-cold-start-read-race | cold-start read race | TBD | — |
| s7-sessions-cross-account | sessions read-path leak | TBD | — |
| s6-rate-limit-login | rate-limit edge (last — pollutes counter) | TBD | — |
| s2-register-immediate-read | register → immediate read (manual, unique email) | TBD | — |

## Triage legend

- **PASS** — поверхность здорова, бага нет
- **FAIL** — устойчивый красный (3/3 прогона) → баг, открыт issue
- **FLAKY** — единичный красный, не воспроизводится → не баг
- **SKIP** — пропуск с причиной (напр. нет сессий для S7)

Порядок прогона: S5 (baseline) → S1 → S3 → S4 → S7 → S6 (последним, загрязняет rate-limit счётчик). S2 — manual, отдельный прогон с уникальным email.