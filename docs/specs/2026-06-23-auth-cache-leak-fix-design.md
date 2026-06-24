# Fix: Auth token cache leak on logout / account switch (#314)

**Дата:** 2026-06-23
**Статус:** Approved
**Связано:** Issue #314, worktree `worktree-auth-cache-logout-bug`
**Отделяется от:** `2026-06-23-mobile-auth-session-test-suite-design.md` (тест-сьют вылавливает баги красными тестами; этот спека — фикс конкретного бага #314)

## Контракт фикса

После любой из операций `logout()` / `login()` / `register()` следующий авторизованный запрос (`users/me`, sessions и т.д.) берёт **свежий** токен из персистентного хранилища, а не закэшированный в памяти `Auth`-плагина. Регрессионный тест `AuthRepositoryCacheBugReproTest.logout_thenLoginAsDifferentUser_getMeReturnsNewUser` позеленеет (ассерт `id == "b"`).

## Корневая причина

Ktor `Auth`-плагин кэширует bearer-токен в памяти (`BearerAuthProvider` → `AuthTokenHolder.value`, lazy `loadTokens` — грузит один раз, дальше отдаёт закэшированное). `AuthRepository` трогает только персистентное хранилище:

- `logout()` → `tokenStorage.clearTokens()`
- `login()` / `register()` → `tokenStorage.saveTokens(...)`

Ни одна из трёх точек не инвалидирует in-memory кэш `Auth`-плагина. Поэтому logout→login другим аккаунтом → `getMe()` уходит со **старым** закэшированным токеном → сервер возвращает профиль прежнего пользователя.

Та же болезнь у прямого переключения аккаунта без logout (login A → login B): кэш держит токен A.

## Решение

Единственный способ сбросить in-memory кэш `Auth`-плагина — `BearerAuthProvider.clearToken()`. Чистить надо во всех трёх точках смены владельца сессии.

### Продакшен-код (3 файла)

**1. `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/SkateLabClient.kt`**

Новый публичный метод — очищает кэш всех `BearerAuthProvider`. Доступ к провайдерам — через ссылку на `AuthConfig`, захваченную во время `install(Auth)` (публичный Ktor API отдаёт провайдеров только через этот config-приёмник, `plugin(Auth)` возвращает `ClientPluginInstance` без `providers`):

```kotlin
private lateinit var authConfig: AuthConfig

// внутри install(Auth) { authConfig = this; bearer { ... } }

fun clearAuthCache() {
    authConfig.providers
        .filterIsInstance<BearerAuthProvider>()
        .forEach { it.clearToken() }
}
```

Импорты: `io.ktor.client.plugins.auth.AuthConfig`, `io.ktor.client.plugins.auth.providers.BearerAuthProvider` (оба покрыты wildcard-импортами `...auth.*` и `...providers.*`, уже присутствующими в файле).

**2. `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/auth/AuthRepository.kt`**

Третий конструктор-параметр со значением по умолчанию (минимум изменений, существующие тесты не трогаются):

```kotlin
class AuthRepository(
    private val authApi: AuthApi,
    private val tokenStorage: TokenStorage,
    private val clearAuthCache: () -> Unit = {},
) {
    suspend fun login(...) = runCatching {
        val tokens = authApi.login(email, password)
        tokenStorage.saveTokens(tokens.accessToken, tokens.refreshToken)
        clearAuthCache()
    }

    suspend fun register(...) = runCatching {
        val tokens = authApi.register(email, password, displayName)
        tokenStorage.saveTokens(tokens.accessToken, tokens.refreshToken)
        clearAuthCache()
    }

    suspend fun logout() {
        val refreshToken = tokenStorage.getRefreshToken()
        if (refreshToken != null) {
            runCatching { authApi.logout(refreshToken) }
        }
        tokenStorage.clearTokens()
        clearAuthCache()
    }
}
```

Вызов `clearAuthCache()` ставится **после** записи/очистки персистентного хранилища, чтобы следующий `loadTokens` гарантированно перечитал свежие токены.

**3. `mobile/androidApp/src/main/java/ru/skatelab/capture/di/AppModule.kt`**

`provideAuthRepository` передаёт третий аргумент:

```kotlin
@Provides
@Singleton
fun provideAuthRepository(
    client: SkateLabClient,
    tokenStorage: TokenStorage,
): AuthRepository =
    AuthRepository(
        client.auth,
        tokenStorage,
        client::clearAuthCache,
    )
```

### Тест (1 файл, позеленеет)

**`mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthRepositoryCacheBugReproTest.kt`**

Уже в worktree (коммит `e8937ff1`, cherry-pick из `40b5ebe9`), падает. После фикса — зелёный. В тесте `AuthRepository` конструируется с третьим аргументом — инлайн-лямбдой, повторяющей логику `SkateLabClient.clearAuthCache()`. Тест собирает `HttpClient` напрямую (без `SkateLabClient`), поэтому захватывает `AuthConfig` внутри своего `install(Auth)`-блока так же, как продакшен-код:

```kotlin
lateinit var authConfig: AuthConfig
// ... HttpClient { install(Auth) { authConfig = this; bearer { ... } } }

val clearCache: () -> Unit = {
    authConfig.providers
        .filterIsInstance<BearerAuthProvider>()
        .forEach { it.clearToken() }
}
val repo = AuthRepository(AuthApi(client), tokenStorage, clearCache)
```

### Не трогается

- 12 существующих `AuthRepositoryTest` — дефолтный `clearAuthCache = {}` сохраняет их поведение. Они не используют `Auth`-плагин, кэша нет, фикс им безразличен.
- UI-слой `AuthViewModel` — собственного кэша токенов не держит, ходит через `UsersApi` → `HttpClient` → `Auth`-плагин. Фикс на уровне repository/client достаточен для всего UI.

## Поток данных (после фикса)

```
logout()
  ├─ tokenStorage.clearTokens()          # персистентное хранилище пусто
  └─ clearAuthCache()                    # in-memory кэш Auth-плагина сброшен
        ↓
login(B)
  ├─ authApi.login() → tokensB
  ├─ tokenStorage.saveTokens(acc-B, ref-B)
  └─ clearAuthCache()                    # кэш снова сброшен → следующий loadTokens перечитает
        ↓
getMe() → Auth-плагин: loadTokens → читает хранилище → acc-B → профиль B ✅
```

## Верификация

1. `:shared:testDebugUnitTest --tests "*AuthRepositoryCacheBugReproTest*"` — зелёный (регрессия).
2. `:shared:testDebugUnitTest --tests "*AuthRepositoryTest*"` — 12 тестов остаются зелёными.
3. `:shared:ktlintCheck` — чисто.
4. Сборка через Docker-fallback `android-apk-builder:local` при нестабильном локальном Gradle daemon (`--no-daemon --no-configuration-cache`).

## Git-стратегия

- Фикс коммитится в worktree `worktree-auth-cache-logout-bug` (как указано в issue).
- В worktree лежат незакоммиченные `FakeAuthBackend.kt` + `FakeAuthBackendSmokeTest.kt` — незавершённая работа тест-сьюта, к фиксу #314 отношения не имеет. В PR фикса **не включаются** (остаются untracked, в `git add` попадают только 3 продакшен-файла + репро-тест).
- Коммиты:
  - `fix(mobile): invalidate Ktor Auth in-memory cache on logout/login/register`
  - Репро-тест уже закоммичен (`40b5ebe9`) и позеленеет тем же коммитом фикса.

## Non-goals

- Тест-сьют из 14 сценариев (`2026-06-23-mobile-auth-session-test-suite-design.md`) — отдельная работа, не в этом PR.
- Backend-изменения (не нужны — баг клиентский).
- Maestro E2E (wire-тест ловит раньше и дешевле; E2E-флоу logout→login в одном процессе можно добавить позже, отдельным PR).