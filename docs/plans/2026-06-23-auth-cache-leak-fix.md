# Auth Token Cache Leak Fix #314 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Invalidate the Ktor `Auth` plugin's in-memory token cache alongside persistent storage on `logout`/`login`/`register`, so switching accounts no longer shows the previous user's profile.

**Architecture:** Add `clearAuthCache()` to `SkateLabClient` (clears all `BearerAuthProvider` in-memory caches via `clearToken()`). Pass it to `AuthRepository` as a `clearAuthCache: () -> Unit = {}` constructor callback. Call it in `logout()`, `login()`, `register()` after touching persistent storage. Wire the callback in `AppModule`. The existing repro test greens.

**Tech Stack:** Kotlin Multiplatform, Ktor 3.1.3 (`io.ktor.client.plugins.auth`), kotlinx-coroutines-test, kotlin-test, multiplatform-settings (`MapSettings`).

## Global Constraints

- **Docker-fallback runner:** when the local Gradle daemon is unstable (OOM / lock-contention / port conflicts — it happens), run inside the `android-apk-builder:local` container. Always `--no-daemon --no-configuration-cache`. Example:
  `docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local bash -c 'chmod +x gradlew && ./gradlew <task> --no-daemon --no-configuration-cache --tests "<filter>"'`
- **Test target for shared (KMP):** `:shared:testDebugUnitTest` is the Android-JVM target that runs `commonTest` sources and accepts `--tests "<FQN>"` filters. CI instead runs `:shared:allTests` (all KMP targets). Both are valid; prefer `:shared:testDebugUnitTest --tests ...` for fast targeted runs. If you see `Timeout waiting to lock file hash cache`, a parallel Gradle process holds the `.gradle/` lock — wait for it to finish or run in a fresh container rather than retrying immediately.
- **ktlint scope — IMPORTANT:** the ktlint plugin (`org.jlleitschuh.gradle.ktlint`) is applied ONLY by `android-app-convention`. The `shared` (KMP library) module does NOT have ktlint — there is NO `:shared:ktlintCheck` task (calling it fails with "task not found"). Root `./gradlew ktlintCheck` runs only `:androidApp` source sets. Therefore:
  - For `shared` files (Tasks 1–3): verification is **compile + tests** (`:shared:compileDebugKotlinAndroid`, `:shared:testDebugUnitTest`). Do NOT run a ktlint task for shared.
  - For `androidApp` files (Task 4): run `:androidApp:ktlintCheck` for real lint coverage.
- **Ktor 3.x gotcha:** `HttpResponse.request` is a function, not a property — never access `response.request.url` in strings; use `response.status` / the `MockEngine` handler's `request` param only.
- **No new dependencies** — `ktor.client.auth`, `ktor.client.mock`, `kotlinx.coroutines.test`, `multiplatform.settings.test` already in `:shared` commonTest.
- **Existing 12 `AuthRepositoryTest` tests are NOT modified** — they use a plain `HttpClient` without the `Auth` plugin (no cache → no bug). The default `clearAuthCache = {}` keeps their behavior identical.
- **Worktree:** `worktree-auth-cache-logout-bug`. All work here. The untracked `FakeAuthBackend.kt` / `FakeAuthBackendSmokeTest.kt` belong to the separate test-suite work and are NOT part of this fix — never `git add` them.
- **Commit message format:** `<type>(<scope>): <description>` — types `fix`/`test`/`docs`, scope `mobile`.

## File Structure

```
mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/
├── api/SkateLabClient.kt        # MODIFY — add clearAuthCache()
└── auth/AuthRepository.kt       # MODIFY — 3rd ctor param + 3 call sites
mobile/androidApp/src/main/java/ru/skatelab/capture/di/
└── AppModule.kt                 # MODIFY — pass client::clearAuthCache
mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/
└── AuthRepositoryCacheBugReproTest.kt  # MODIFY — pass clearCache lambda (greens)
```

Responsibilities:
- **`SkateLabClient.clearAuthCache()`** — single owner of "reset Auth plugin in-memory cache". Iterates `httpClient.plugin(Auth).providers`, clears every `BearerAuthProvider`.
- **`AuthRepository`** — owns the three state-transition points (`logout`/`login`/`register`); delegates cache reset to the injected callback. No knowledge of Ktor internals.
- **`AppModule.provideAuthRepository`** — the single wiring point binding the client's cache-reset to the repository.

---

## Task 1: Add `clearAuthCache()` to `SkateLabClient`

**Files:**
- Modify: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/SkateLabClient.kt` (after line 99, before final `}`)

**Interfaces:**
- Produces: `fun SkateLabClient.clearAuthCache(): Unit` — clears all `BearerAuthProvider` in-memory caches. No params, no return. Consumed by Task 2 (via `client::clearAuthCache` reference) and Task 3 (AppModule wiring).

**Context:** `SkateLabClient` already imports `io.ktor.client.plugins.auth.*` and `io.ktor.client.plugins.auth.providers.*` (lines 8–9), so `Auth` and `BearerAuthProvider` are available without new imports. `httpClient` is a `val` on the class (line 31). The method goes after the API properties (line 98) and before the closing brace (line 99).

- [ ] **Step 1: Add the method**

Insert after line 98 (`val metrics = MetricsApi(httpClient)`) and before the final `}`:

```kotlin
    /**
     * Clear the Ktor `Auth` plugin's in-memory bearer-token cache.
     *
     * The plugin caches the loaded token in memory (`BearerAuthProvider` →
     * `AuthTokenHolder.value`) and only reloads from storage once per process
     * lifetime. After logout or login as a different account, the cache holds a
     * stale token, so authorized requests reuse it and hit the wrong user.
     * Call this whenever the session owner changes so the next authorized
     * request forces `loadTokens` to re-read storage.
     */
    fun clearAuthCache() {
        httpClient.plugin(Auth).providers
            .filterIsInstance<BearerAuthProvider>()
            .forEach { it.clearToken() }
    }
```

- [ ] **Step 2: Verify it compiles**

Run:
```bash
docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local \
  bash -c 'chmod +x gradlew && ./gradlew :shared:compileDebugKotlinAndroid --no-daemon --no-configuration-cache' 2>&1 | tail -20
```
Expected: `BUILD SUCCESSFUL`. If `BUILD FAILED`, read the `e: file://...` lines — the only likely cause is a typo in `BearerAuthProvider`/`clearToken`/`plugin(Auth)`, all already covered by the wildcard imports. (No ktlint step — `shared` has no ktlint plugin; see Global Constraints.)

- [ ] **Step 3: Commit**

```bash
git add mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/SkateLabClient.kt
git commit -m "feat(mobile): add clearAuthCache() to SkateLabClient"
```

---

## Task 2: Wire `clearAuthCache` callback into `AuthRepository`

**Files:**
- Modify: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/auth/AuthRepository.kt` (full file, 38 lines)

**Interfaces:**
- Consumes: `clearAuthCache: () -> Unit` callback (from Task 1's `SkateLabClient.clearAuthCache()`).
- Produces: `AuthRepository(authApi, tokenStorage, clearAuthCache = ...)` with a defaulted 3rd parameter. The default `{}` keeps existing 2-arg call sites (the 12 `AuthRepositoryTest`s) compiling unchanged.

**Context:** Current `AuthRepository` has only `authApi` + `tokenStorage`. The callback is defaulted so the 12 existing tests (which never install the `Auth` plugin) need no edits. Call the callback AFTER the persistent-storage write/clear so the next `loadTokens` re-reads storage.

- [ ] **Step 1: Replace the file with the wired version**

Replace the entire contents of `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/auth/AuthRepository.kt`:

```kotlin
package ru.skatelab.shared.auth

import ru.skatelab.shared.api.AuthApi

class AuthRepository(
    private val authApi: AuthApi,
    private val tokenStorage: TokenStorage,
    private val clearAuthCache: () -> Unit = {},
) {
    suspend fun getAccessToken(): String? = tokenStorage.getAccessToken()

    suspend fun login(email: String, password: String): Result<Unit> = runCatching {
        val tokens = authApi.login(email, password)
        tokenStorage.saveTokens(tokens.accessToken, tokens.refreshToken)
        clearAuthCache()
    }

    suspend fun register(email: String, password: String, displayName: String): Result<Unit> = runCatching {
        val tokens = authApi.register(email, password, displayName)
        tokenStorage.saveTokens(tokens.accessToken, tokens.refreshToken)
        clearAuthCache()
    }

    suspend fun isLoggedIn(): Boolean = tokenStorage.getAccessToken() != null

    suspend fun logout() {
        val refreshToken = tokenStorage.getRefreshToken()
        if (refreshToken != null) {
            runCatching { authApi.logout(refreshToken) }
        }
        tokenStorage.clearTokens()
        clearAuthCache()
    }

    suspend fun verifyEmail(token: String): Result<Unit> = runCatching { authApi.verifyEmail(token) }

    suspend fun resendVerification(email: String): Result<Unit> = runCatching { authApi.resendVerification(email) }

    suspend fun forgotPassword(email: String): Result<Unit> = runCatching { authApi.forgotPassword(email) }

    suspend fun resetPassword(token: String, newPassword: String): Result<Unit> = runCatching { authApi.resetPassword(token, newPassword) }
}
```

- [ ] **Step 2: Verify existing tests still compile and pass**

The 12 `AuthRepositoryTest` tests construct `AuthRepository(AuthApi(client), tokenStorage)` (2-arg) — must still work via the default `{}`.

Run:
```bash
docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local \
  bash -c 'chmod +x gradlew && ./gradlew :shared:testDebugUnitTest --no-daemon --no-configuration-cache --tests "ru.skatelab.shared.auth.AuthRepositoryTest" 2>&1 | tail -25'
```
Expected: `BUILD SUCCESSFUL`, 12 tests passed. If any fail, the regression is in the edit — re-check the 3 call sites are after the storage mutation and the signature is exactly `private val clearAuthCache: () -> Unit = {}`. (No ktlint step — `shared` has no ktlint plugin; see Global Constraints.)

- [ ] **Step 3: Commit**

```bash
git add mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/auth/AuthRepository.kt
git commit -m "fix(mobile): invalidate Ktor Auth cache on logout/login/register"
```

---

## Task 3: Green the repro test (pass the callback)

**Files:**
- Modify: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthRepositoryCacheBugReproTest.kt` (add imports + change repo construction at line 98)

**Interfaces:**
- Consumes: `AuthRepository`'s 3rd constructor param `clearAuthCache: () -> Unit` (from Task 2). The `Auth` plugin + `BearerAuthProvider` types from ktor-client-auth (already in commonTest transitively).

**Context:** The test currently constructs `val repo = AuthRepository(AuthApi(client), tokenStorage)` (line 98) — 2-arg, so it uses the default `{}` and the test stays RED (cache never cleared). The fix passes a lambda that mirrors `SkateLabClient.clearAuthCache()`. The test already imports `io.ktor.client.plugins.auth.Auth` (line 7) and `io.ktor.client.plugins.auth.providers.bearer` (line 9). Add an import for `BearerAuthProvider` (same package as `BearerTokens`, already imported on line 8).

The repro test's own assertion (lines 110–117) already asserts `id == "b"` — it needs no change. Only the repo construction changes, which makes the assertion pass.

- [ ] **Step 1: Add the `BearerAuthProvider` import**

In `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthRepositoryCacheBugReproTest.kt`, after line 9 (`import io.ktor.client.plugins.auth.providers.bearer`), add:

```kotlin
import io.ktor.client.plugins.auth.providers.BearerAuthProvider
```

- [ ] **Step 2: Replace the repo construction with the wired version**

In the same file, replace line 98:

```kotlin
        val repo = AuthRepository(AuthApi(client), tokenStorage)
```

with:

```kotlin
        // Mirror SkateLabClient.clearAuthCache(): clear the Auth plugin's in-memory
        // cache so logout/login forces loadTokens to re-read storage.
        val clearCache: () -> Unit = {
            client.plugin(Auth).providers
                .filterIsInstance<BearerAuthProvider>()
                .forEach { it.clearToken() }
        }
        val repo = AuthRepository(AuthApi(client), tokenStorage, clearCache)
```

- [ ] **Step 3: Run the repro test — verify it now PASSES**

Run:
```bash
docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local \
  bash -c 'chmod +x gradlew && ./gradlew :shared:testDebugUnitTest --no-daemon --no-configuration-cache --tests "ru.skatelab.shared.auth.AuthRepositoryCacheBugReproTest" 2>&1 | tail -25'
```
Expected: `BUILD SUCCESSFUL`, `logout_thenLoginAsDifferentUser_getMeReturnsNewUser` PASSED.

If it still FAILS with `expected:<[b]> but was:<[a]>`, the cache is not being cleared — confirm the lambda uses `clearToken()` (not a no-op) and the import is `BearerAuthProvider` (not `BearerTokens`). If it fails on compile, the import is missing or misspelled. (No ktlint step — `shared` has no ktlint plugin; see Global Constraints.)

- [ ] **Step 4: Commit**

```bash
git add mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthRepositoryCacheBugReproTest.kt
git commit -m "test(mobile): green repro #314 by clearing Auth cache in AuthRepository"
```

---

## Task 4: Wire the callback in `AppModule`

**Files:**
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/di/AppModule.kt` (lines 127–134, `provideAuthRepository`)

**Interfaces:**
- Consumes: `SkateLabClient.clearAuthCache()` (Task 1) and the 3-arg `AuthRepository` ctor (Task 2).

**Context:** `provideAuthRepository` already receives `client: SkateLabClient` (line 128). It currently constructs `AuthRepository(client.auth, tokenStorage)` (2-arg). Add `client::clearAuthCache` as the 3rd argument.

- [ ] **Step 1: Update the provider**

In `mobile/androidApp/src/main/java/ru/skatelab/capture/di/AppModule.kt`, replace the body of `provideAuthRepository` (lines 131–134):

```kotlin
            AuthRepository(
                client.auth,
                tokenStorage,
            )
```

with:

```kotlin
            AuthRepository(
                client.auth,
                tokenStorage,
                client::clearAuthCache,
            )
```

- [ ] **Step 2: Verify the android app compiles + DI wiring resolves**

Run:
```bash
docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local \
  bash -c 'chmod +x gradlew && ./gradlew :androidApp:compileDebugKotlin --no-daemon --no-configuration-cache' 2>&1 | tail -20
```
Expected: `BUILD SUCCESSFUL`. Hilt/KSP runs as part of Kotlin compilation; if `client::clearAuthCache` is unresolved, confirm Task 1 was committed (the method exists on `SkateLabClient`). If `compileDebugKotlin` is somehow unavailable in this checkout, fall back to `:androidApp:assembleDebug` (documented in `mobile/CLAUDE.md`) which additionally links the full APK and exercises the Hilt graph end-to-end.

- [ ] **Step 3: ktlint**

Run:
```bash
docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local \
  bash -c 'chmod +x gradlew && ./gradlew :androidApp:ktlintCheck --no-daemon --no-configuration-cache' 2>&1 | tail -20
```
Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/di/AppModule.kt
git commit -m "fix(mobile): wire clearAuthCache into AuthRepository via DI"
```

---

## Task 5: Full verification + push

**Files:** none (verification only)

- [ ] **Step 1: Full shared test suite**

Run the entire `:shared` test suite to confirm no collateral damage:
```bash
docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local \
  bash -c 'chmod +x gradlew && ./gradlew :shared:testDebugUnitTest --no-daemon --no-configuration-cache 2>&1 | tail -25'
```
Expected: `BUILD SUCCESSFUL`. Confirm both `AuthRepositoryTest` (12) and `AuthRepositoryCacheBugReproTest` (1 green) pass, plus all other shared tests.

- [ ] **Step 2: androidApp ktlint + compile (covers the AppModule change)**

Run:
```bash
docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local \
  bash -c 'chmod +x gradlew && ./gradlew :androidApp:ktlintCheck :androidApp:compileDebugKotlin --no-daemon --no-configuration-cache' 2>&1 | tail -20
```
Expected: `BUILD SUCCESSFUL`. This is the only real ktlint gate in the project (ktlint is not applied to `shared`; see Global Constraints).

- [ ] **Step 3: Confirm only the 4 intended files changed (FakeAuthBackend excluded)**

Run:
```bash
git status -s
```
Expected working tree to show ONLY these tracked changes already committed, and `FakeAuthBackend.kt` / `FakeAuthBackendSmokeTest.kt` remain UNTRACKED (not added). If they were accidentally staged, unstage them:
```bash
git restore --staged mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/FakeAuthBackend.kt mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/FakeAuthBackendSmokeTest.kt
```

- [ ] **Step 4: Pre-push: fetch + merge origin/master**

```bash
git fetch origin && git merge origin/master
```
Expected: either "Already up to date" or a clean fast-forward; no conflicts. If conflicts, resolve keeping the fix intact and re-run Task 5 Step 1.

- [ ] **Step 5: Push**

```bash
git push -u origin worktree-auth-cache-logout-bug
```

- [ ] **Step 6: Open PR**

```bash
gh pr create --base master --title "fix(mobile): invalidate Ktor Auth cache on logout/login/register (#314)" --body "$(cat <<'EOF'
## Что сделано
- `SkateLabClient.clearAuthCache()`: очищает in-memory кэш `BearerAuthProvider` (`clearToken()`).
- `AuthRepository`: 3-й параметр `clearAuthCache: () -> Unit = {}`, вызов в `logout`/`login`/`register` после записи/очистки персистентного хранилища.
- `AppModule`: передаёт `client::clearAuthCache` в `AuthRepository`.
- Репро-тест #314 позеленел (регрессия); 12 существующих `AuthRepositoryTest` не тронуты (дефолт `{}`).

Fixes #314.

## Как проверить
- `:shared:testDebugUnitTest --tests "*AuthRepositoryCacheBugReproTest*"` → зелёный.
- `:shared:testDebugUnitTest --tests "*AuthRepositoryTest*"` → 12 зелёных.
- `:androidApp:ktlintCheck :androidApp:compileDebugKotlin` → чисто (ktlint применяется только к androidApp; `shared` не линтится).
- Сценарий: login A → logout → login B → профиль показывает B (раньше показывал A).
EOF
)"
```
Expected: PR created. CI (`mobile.yml`) will run shared tests, Android lint/test, APK build.