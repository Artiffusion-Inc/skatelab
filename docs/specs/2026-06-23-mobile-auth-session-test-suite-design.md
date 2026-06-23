# Mobile Auth/Session Integration Test Suite — Design

**Дата:** 2026-06-23
**Статус:** Approved
**Связано:** Issue #314 (auth token cache leak — подтверждённый repro), worktree `worktree-auth-cache-logout-bug`

## Контекст и мотивация

При выходе mobile-приложения в prod выявлен баг (#314): после logout из аккаунта `test@skatelab.ru` и логина в другой аккаунт профиль показывает прежнего пользователя. Корневая причина — Ktor `Auth`-плагин кэширует bearer-токен в памяти (`AuthTokenHolder.value`, lazy `loadTokens`), а `AuthRepository.logout/login` чистят только персистентное хранилище.

Баг проскользнул мимо 14 существующих `shared/AuthViewModelTest` — те используют реальный `HttpClient`+`Auth`-плагин, но ассертят **state-переходы**, а не **какой токен реально уходит в запрос**. Аналогично не покрыт весь refresh-token flow (401→refresh→retry, refresh-ротация, concurrent refresh, refresh-failure→logout) — ни одного теста на `auth/refresh`.

Цель spec'а — закрыть prod-критичные дыры в auth-ядре и session read-path мобильного приложения через **интеграционный тест-сет с реальным Auth-плагином**, где каждый упавший сценарий становится отдельным issue с полным repro.

## Решение (Approach A — Approved)

Тесты гоняются против `HttpClient` с **реально установленным `Auth`-плагином** (как в `SkateLabClient`) поверх `MockEngine`. `MockEngine` маршрутизирует запросы по **фактически отправленному `Authorization`-заголовку и пути** — если плагин подставил не тот токен, заглушка возвращает не тот профиль, и assertion падает. Моков `AuthRepository`/`UsersApi`/`SessionsApi` нет — только тонкая заглушка сервера `FakeAuthBackend`.

Альтернативы отклонены:
- **B (state-тесты на ViewModel)** — усиливает существующее слепое пятно (state-переходы уже покрыты и именно пропустили баг).
- **C (property-based/fuzzing)** — оверкилл, новый деп, шум без ясных repro.

## Архитектура

Один новый нетестовый компонент — **`FakeAuthBackend`** (в commonTest, не продакшен-код). Инкапсулирует boilerplate маршрутизации `MockEngine`:

- знает эндпоинты `auth/login`, `auth/logout`, `auth/refresh`, `users/me`, `users/me/settings`, `sessions`, `sessions/{id}`
- каждому аккаунту назначает пару токенов (`acc-X/ref-X`)
- по `Authorization: Bearer X` отдаёт профиль/сессии владельца этого токена
- управляет состоянием: жив ли refresh, сколько раз дёргался refresh, отозван ли access (вернуть 401)
- API состояния: `expireAccessToken(account)`, `revokeRefreshToken(account)`, `setRefreshResponse(...)`
- токены — строковые константы, без `Date.now`/`Math.random` (недоступны в workflow-контексте)

Тесты тонкие: создают `FakeAuthBackend`, конфигурируют аккаунты/истечение, дёргают repository/api, ассертят.

### Два уровня тестов

- **`AuthWireTest`** (shared/commonTest/auth) — wire-уровень: `AuthRepository` + `UsersApi` + реальный `Auth`-плагин. Сценарии #1–#10 (auth-ядро + refresh). Сюда входит расширенный repro #314.
- **`SessionReadAuthTest`** (shared/commonTest/state) — read-path сессий: `SessionsApi.list/detail` против `FakeAuthBackend`. Сценарии #11–#14.

Оба — JVM-таргет (`:shared:testDebugUnitTest`), детерминированные, в CI.

## Структура файлов

```
mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/
├── auth/
│   ├── FakeAuthBackend.kt          # NEW — routing engine + account state
│   └── AuthWireTest.kt             # NEW — сценарии #1–#10
└── state/
    └── SessionReadAuthTest.kt      # NEW — сценарии #11–#14
```

`AuthRepositoryCacheBugReproTest.kt` (существующий repro #314) поглощается сценарием #1 в `AuthWireTest` — удаляется как отдельный файл, логика переносится.

## Поток данных

```
Test ──► FakeAuthBackend (accounts + token state)
         │  routes by path + Authorization header
         │  auth/login    → issue tokens for that account, increment login counter
         │  auth/logout   → optionally revoke that account's refresh
         │  auth/refresh  → if refresh valid: rotate tokens, return new pair
         │                  if dead: 401
         │  users/me      → profile of token's owner
         │  sessions      → sessions of token's owner
         └─ HttpClient (real Auth plugin) ──► SkateLabClient wiring ──► AuthRepository / UsersApi / SessionsApi
```

## Сценарии (14)

### Auth-cache / multi-account
1. `logoutThenLoginAsDifferentUser_getMeReturnsNewUser` — из #314, регрессия.
2. `logoutThenLoginSameUser_getMeSucceeds` — контроль: кэш сбрасывается корректно.
3. `logout_clearsInMemoryTokenCache` — после logout авторизованный запрос не уходит со старым токеном.
4. `registerAfterLogout_getMeReturnsNewUser` — register-путь той же болезни.
5. `switchAccountTwice_getMeMatchesLatestLogin` — A→logout→B→logout→A: финал = A.

### Refresh-token flow (нулевое покрытие — наибольший риск)
6. `expiredAccess_liveRefresh_getMeRetriesWithNewToken` — 401 на access, refresh жив → retry → профиль.
7. `expiredAccessAndRefresh_onAuthFailureTriggersLogout` — оба мертвы → `onAuthFailure` → `LoggedOut`.
8. `concurrentRequestsOnExpiringToken_refreshCalledOnce` — 2 одновременных запроса: refresh один раз.
9. `refreshReturnsNewRefreshToken_storageUpdated` — ротация: сохранена новая пара.
10. `refreshFailureThenSuccess_doesNotLeakStaleState` — refresh 500 → восстановление сети → успешный refresh.

### Session read-path
11. `sessionsList_usesCurrentAccountToken` — список соответствует текущему аккаунту.
12. `sessionDetail_afterAccountSwitch_belongsToNewAccount` — деталь не «протекает» из старого.
13. `sessionsList_on401_refreshesTransparently` — 401 → refresh → retry, без ошибки юзеру.
14. `sessionsList_afterLogout_failsCleanly` — запрос без валидного токена → `AppError.Auth`, не чужой профиль.

**Ожидаемая доля падающих:** refresh-flow (#6–#10) — высокая; auth-cache (#2–#5) — средняя; session read-path (#11–#14) — низкая-средняя.

## Обработка ошибок

Все ошибки маппятся через реальную цепочку (Ktor `ResponseException` → `toAppError()`), без моков. Assertions на `AppError`-типах:
- 401 на access при мёртвом refresh → `onAuthFailure` → `LoggedOut` (#7)
- сетевая ошибка (MockEngine кидает `IOException`) → `AppError.Network`/`Timeout`
- `AppError.Unknown` с утечкой — сигнал, что exception прорвался мимо sealed-маппинга (недопустимо)

Упавшие сценарии — `@Test` без подавления, падают явно → issue.

## Тестирование (мета)

- Таргет: `:shared:testDebugUnitTest` (JVM), часть существующего CI-код-чека.
- Новый деп не нужен: `ktor-client-auth`, `MockEngine`, `kotlinx-coroutines-test` уже в commonTest.
- TDD-порядок: `FakeAuthBackend` → сценарии по одному. Продакшен-баги = красные тесты, остаются красными в worktree.
- Kover-порог не трогаем — цель не метрика, а найденные баги.
- Сборка через Docker-fallback `android-apk-builder:local` при нестабильном локальном Gradle daemon.

## Workflow: баг → issue

Каждый упавший сценарий → issue с тэгом `testing/repro` по шаблону #314:
1. Что произошло (one-liner сценария)
2. Корневая причина (trace по коду)
3. Repro: ссылка на тест + git-коммит в worktree
4. Предлагаемый фикс
5. Влияние на prod
6. Branch

Коммит-стратегия: один коммит на сценарий — `test(mobile): repro for <scenario>`. Issue создаётся после подтверждения теста красным локально. Падающий тест коммитится и **остаётся красным** в worktree (доказательство для reviewer); зелёным станет в PR-фиксе. Фиксы — отдельными PR по issue, не в этом worktree.

## Non-goals

- Фиксы найденных багов (отдельные PR/issue).
- Backend-тесты (отдельная область).
- Upload pipeline, navigation backstack, profile-edit flow (out of scope).
- Property-based/fuzzing (отклонён).
- Maestro-флоу для этих сценариев (E2E — отдельный слой; wire-тесты ловят раньше и дешевле).
- Изменение продакшен-кода в этом spec'е (только `FakeAuthBackend` в commonTest).

## Worktree

`worktree-auth-cache-logout-bug` — уже содержит repro #314 (коммит `40b5ebe9`). Сюда же пишется весь тест-сет.