# E2E Bug-Hunt Index — session lifecycle

Bug-hunt E2E-набор гоняет полный цикл пользовательской сессии против реального backend `api.skatelab.ru`, чтобы выявлять **новые** (неизвестные) недоработки в mobile и backend. Каждую найденную недоработку → issue с тегом для reviewer. Production-код не трогается (мандат: диагностика + тесты + issues).

Прогон: 2026-06-24, эмулятор `skatelab-emulator`, реальный backend `api.skatelab.ru`, debug APK (md5 `5edcaf8d59e42a2405f0584bb0a83b5a`).

## Preconditions

- **Backend:** `https://api.skatelab.ru/v1/` (реальный, живой)
- **Аккаунт A:** `test@skatelab.ru` / `Test123456` (`is_verified=true`)
- **Аккаунт B:** `e2e2@skatelab.ru` / `Test123456` (`is_verified=true`, создан 2026-06-24 через `/auth/register` + `UPDATE users SET is_verified=true` в prod-DB `infra-postgres-1` — test-fixture setup)
- **Эмулятор:** `skatelab-emulator` (budtmo/docker-android:emulator_14.0), Maestro 2.6.x в контейнере
- **APK:** debug-сборка с `API_BASE_URL=https://api.skatelab.ru/v1/`

## Triage results

Порядок прогона: S5 (baseline) → S1 → S3 → S4 → S7 → S6. S2 — manual (уникальный email, не прогонялся в suite).

| Flow | Сценарий | Статус | Issue | Примечание |
|------|----------|--------|-------|------------|
| s5-relogin-same-baseline | re-login same account (baseline) | **PASS** | — | Инфра работает, базовый цикл здоров. |
| s1-cross-account-switch | cross-account switch (A→B) | **FAIL** | **#328** | Сквозное E2E-подтверждение #314: Profile показывает A после login B. Backend корректен (проверено), mobile отправляет stale токен. |
| s3-read-after-logout | read after logout (UI state leak) | **PASS** | — | Logout очищает UI-состояние; после relaunch login screen, не sessions A. Поверхность logout→relaunch здорова. |
| s4-cold-start-read-race | cold-start read race | **PASS** | — | Cold-start race не даёт stale/inconsistent; Profile показывает A корректно. Поверхность холодного старта здорова. |
| s7-sessions-cross-account | sessions read-path leak | **FAIL** | **#327** | Login form не очищает email-поле / error-message после logout/failed-login → malformed email → 401. Новая находка (UI-state leak, не token-cache). |
| s6-rate-limit-login | rate-limit edge | **FAIL (dup of #327)** | #327 | Та же болезнь #327: после failed login кнопка "Log in" → "Retry", email-поле не очищено → `tapOn: "Log in"` не находит элемент на 2-й итерации. Не отдельный баг — проявление #327. (Rate-limit handling как таковой не верифицирован из-за этого блокера — отдельный прогон после фикса #327.) |
| s2-register-immediate-read | register → immediate read (manual, unique email) | **PASS** | — | Manual прогон 2026-06-24 с уникальным email `e2e-20260624-s2b@skatelab.ru`: register → немедленный Profile показывает свежий аккаунт корректно. Register→read здоров (нет stale-кэша после register — register выдаёт свежие токены, в отличие от logout→login). |

## Найденные недоработки (новые / подтверждённые)

### #327 — Login form state leak (НОВАЯ)
После logout/failed-login экран входа сохраняет stale состояние: email-поле содержит склеенный текст предыдущих вводов, error-сообщение не сбрасывается. UI-state leak (отличается от #314 token-cache leak). Подтверждено S7 и S6.
- Flow: `s7-sessions-cross-account.yaml`, `s6-rate-limit-login.yaml`
- Root cause: `LoginScreen.kt` / `AuthViewModel` не сбрасывают email-поле + `AppError` при logout / retry / открытии login screen.
- Fix (отдельным PR): очищать поля + AppError в AuthViewModel/LoginScreen при logout, переходе на login screen, начале новой попытки.

### #328 — Cross-account profile leak (E2E-подтверждение #314, prod-impact)
Сквозной E2E против реального backend подтверждает #314 в проде: login A → logout → login B → Profile показывает A (не B). Backend корректен (проверено прямой curl-диагностикой — `/users/me` с токеном B возвращает B), mobile отправляет stale токен A.
- Flow: `s1-cross-account-switch.yaml`
- Root cause: Ktor Auth-плагин in-memory token cache (`BearerAuthProvider`/`AuthTokenHolder`) не инвалидируется из `AuthRepository.logout/login/register` (= #314).
- Impact: data leak / security-adjacent — пользователь видит профиль прежнего аккаунта после переключения.
- Fix (отдельным PR): `SkateLabClient.clearAuthCache()` + вызов из `AuthRepository.logout/login/register`. См. `docs/specs/2026-06-23-auth-cache-leak-fix-design.md`.

## Здоровые поверхности (PASS)

- **S3** — logout → relaunch: UI-состояние (sessions) корректно сбрасывается, login screen показывается.
- **S4** — cold-start race: Profile/Sessions консистентны после холодного старта, stale-состояния нет.
- **S5** — baseline re-login same account: базовый цикл здоров (инфра-валидация).

## Не верифицировано

- **S6 rate-limit handling** — блокирован #327 (не дошёл до проверки rate-limit-обработки). Повторить после фикса #327.
- **S2** верифицирован 2026-06-24 (PASS) — см. таблицу выше.

## Triage legend

- **PASS** — поверхность здорова, бага нет
- **FAIL** — устойчивый красный → баг, открыт issue
- **FLAKY** — единичный красный, не воспроизводится → не баг
- **SKIP** — пропуск с причиной

Порядок прогона: S5 (baseline) → S1 → S3 → S4 → S7 → S6 (последним — загрязняет rate-limit счётчик; заблокирован #327 до проверки). S2 — manual, отдельный прогон с уникальным email (верифицирован 2026-06-24, PASS).