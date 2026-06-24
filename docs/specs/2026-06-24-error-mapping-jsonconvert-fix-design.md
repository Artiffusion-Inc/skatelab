# Fix: 4xx error-body deserializes to JsonConvertException → AppError.Unknown (#316, #321, #323)

**Дата:** 2026-06-24
**Статус:** Approved
**Связано:** Issues #316, #321, #323; PR #329 (auth-cache fix)
**Worktree:** `auth-cache-fix-verify`

## Контракт фикса

Запрос к `UsersApi.getMe()` / `SessionsApi.get()` / `SessionsApi.list()` и пр. на 4xx-ответ (401 unauthorized, 404 not found) с JSON error-body `{"detail":"..."}` кидает `JsonConvertException` (десериализация error-body в `UserResponse`/`SessionResponse` падает — не хватает обязательных полей). Это **не** `ResponseException`, поэтому `Throwable.toAppError()` маппит его в `AppError.Unknown` вместо `AppError.Auth` / `AppError.NotFound`. После фикса: на 4xx API-метод кидает `ResponseException` (как `AuthApi`), `toAppError()` маппит по HTTP-статусу корректно.

Покрывается тестами:
- `AuthWireTest.logout_clearsInMemoryTokenCache` (#316) — после logout `getMe()` → 401 → `ResponseException` (тест ловит `ResponseException`).
- `SessionReadAuthTest.sessionDetail_afterAccountSwitch_belongsToNewAccount` (#323) — `sessions.get("b-sess-1")` со stale-токеном → 404 → `ResponseException`. Cache-часть уже решена в PR #329; mapping-часть — этот фикс.
- `AuthWireTest.expiredAccessAndRefresh_onAuthFailureTriggersLogout` (#321) — dead-refresh 401 → `onAuthFailure` → `LoggedOut` (статус 401 виден как `AppError.Auth`).

## Корневая причина

`AuthApi` проверяет статус (`if (!response.status.isSuccess()) throw ResponseException(...)`) перед `.body()`. `UsersApi`/`SessionsApi`/`MetricsApi`/`UploadsApi`/`ProcessApi` делают голый `.body<T>()` без проверки → на 4xx с error-body ktor пытается десериализовать тело в success-модель → `JsonConvertException` (`ContentConvertException`). `toAppError()` не имеет ветки для `ContentConvertException` → `else` → `AppError.Unknown`. HTTP-статус при этом **теряется** (deserialization failure не несёт статус).

## Решение

### Production-код

**1. `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/utils/HttpExtensions.kt` (NEW)**

Один extension — DRY-факторизация паттерна из `AuthApi`:

```kotlin
package ru.skatelab.shared.utils

import io.ktor.client.plugins.ResponseException
import io.ktor.client.statement.HttpResponse

/**
 * Throws [ResponseException] if the response status is not a success (2xx),
 * otherwise returns the receiver. Call before `.body<T>()` so a 4xx error-body
 * (e.g. `{"detail":"..."}`) surfaces as a [ResponseException] — mapped by
 * [Throwable.toAppError] to [ru.skatelab.shared.models.AppError.Auth] / NotFound /
 * Server by HTTP status — instead of a [io.ktor.serialization.JsonConvertException]
 * (deserializing the error body into the success model) that falls through to
 * [ru.skatelab.shared.models.AppError.Unknown].
 */
fun HttpResponse.expectSuccess(): HttpResponse {
    if (!status.isSuccess()) {
        throw ResponseException(this, status.description)
    }
    return this
}
```

**2. JSON API-методы** — заменить голый `.body()` на `.expectSuccess().body()`:
- `UsersApi.kt` (3 метода: getMe, updateProfile, updateSettings)
- `SessionsApi.kt` (4 метода: get, list, create, update)
- `MetricsApi.kt` (5 методов)
- `UploadsApi.kt` (2 метода)
- `ProcessApi.kt` (2 JSON-метода: list, getStatus) — **НЕ** трогать streaming `ByteReadChannel` (`response.body()` на line 55, не десериализация).

`AuthApi` уже проверяет статус — не трогать (можно опционально переработать на `expectSuccess()`, но YAGNI; оставить как есть).

### Тест

Существующие `AuthWireTest.logout_clearsInMemoryTokenCache` (#316) и `SessionReadAuthTest.sessionDetail_afterAccountSwitch_belongsToNewAccount` (#323) уже ловят `ResponseException` — после фикса они позеленеют (сейчас кидают `JsonConvertException`). Никаких новых тестов не нужно — repro-сценарии уже в worktree.

Дополнительно: `AuthWireTest.expiredAccessAndRefresh_onAuthFailureTriggersLogout` (#321) — проверяет, что dead-refresh путь вызывает `onAuthFailure`. После фикса 401 на `getMe()` кидает `ResponseException` (а не `JsonConvertException`), что уже обрабатывается `runCatching` → `onAuthFailure`. Должен остаться/позеленеть.

## Поток данных (после фикса)

```
getMe() → 401 with {"detail":"Unauthorized"}
  └─ client.get("users/me").expectSuccess()  // status 401 → throws ResponseException
        ↓ toAppError()
     HttpStatusCode 401 → AppError.Auth ✅
  (раньше: .body<UserResponse>() → JsonConvertException → AppError.Unknown ❌)
```

## Non-goals

- Streaming-методы (`ProcessApi` upload byte-channel) — не JSON, не трогаем.
- Refactoring `AuthApi` на `expectSuccess()` (YAGNI, уже работает).
- Изменение `toAppError()` (не нужно — `ResponseException` уже маппится корректно).
- Backend-изменения (баг клиентский).

## Верификация

1. `:shared:testDebugUnitTest --tests "*AuthWireTest" --tests "*SessionReadAuthTest"` → все 14 зелёные (0 failures).
2. Полный `:shared:testDebugUnitTest` → 0 failures (вкл. существующие UsersApi/SessionsApi-тесты, которые не должны регрессировать — для 2xx `expectSuccess()` no-op).
3. `:androidApp:compileDebugKotlin` → wiring не сломан.