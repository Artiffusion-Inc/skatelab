package ru.skatelab.shared.state

import app.cash.turbine.test
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.MetricsApi
import ru.skatelab.shared.api.SessionsApi
import ru.skatelab.shared.api.UsersApi
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.viewmodel.DashboardViewModel
import kotlin.test.Test
import kotlin.test.assertIs

/**
 * Repro for NEW bug — Dashboard silently swallows auth-failure (401) as "empty data".
 *
 * Root cause: `DashboardViewModel.loadDashboardData()` wraps EVERY backend call in
 * `async { runCatching { ... } }` and recovers with `getOrDefault(null)` / `getOrElse { empty }`
 * (DashboardViewModel.kt:41-52). This treats ALL failures identically — a 401 Unauthorized on
 * `/users/me` becomes `user = null` inside `DashboardState.Loaded(...)`, with NO error surfaced.
 *
 * Contrast: `SessionsViewModel.loadSessions()` uses `catch (e) { Error(e.toAppError()) }`
 * (SessionsViewModel.kt:44-46) → a 401 surfaces as `SessionsUiState.Error(AppError.Auth())`,
 * which the UI maps to a re-login flow. `ExceptionMapping.toAppError()` maps 401/403/400/422 →
 * `AppError.Auth()`. So the Sessions screen correctly tells the user "you're not authenticated,
 * log in again"; the Dashboard screen, for the SAME 401, shows a blank dashboard (user=null,
 * empty PRs/diagnostics/sessions) with no auth signal and no path to re-login.
 *
 * User-impact: a user whose token expired mid-session (or any stale-token path post-#329 corner)
 * opens the Dashboard tab and sees an empty screen — they cannot tell they're logged out, there
 * is no "Log in again" affordance, and the data never refreshes until a manual logout+login.
 * Switching to the Sessions tab would show `Error(Auth)` for the same expired token — an
 * inconsistent, confusing recovery story across tabs.
 *
 * The existing `DashboardViewModelTest.usersApiFails_showsLoadedWithNullUserAndOtherData` only
 * covers HTTP 500 (InternalServerError) — a server fault where "graceful degradation to empty" is
 * arguably reasonable. It does NOT cover 401, where the correct contract is to surface an auth
 * error (the user is unauthenticated, not merely "the server had a hiccup").
 *
 * This test pins the 401 contract: with `/users/me` returning 401 (and other endpoints OK), the
 * Dashboard MUST transition to `DashboardState.Error(AppError.Auth)` — NOT silently `Loaded(null)`.
 * RED now: the current code yields `Loaded(user=null)` (swallowed 401). After the fix — distinguishing
 * auth failures (401/403) from data failures inside `loadDashboardData` and surfacing them as
 * `Error(AppError.Auth())` — this goes GREEN.
 *
 * Proposed fix (separate PR, not this one): in `loadDashboardData`, do not blanket-`runCatching`
 * the `usersApi.getMe()` call. Let a 401/403 propagate to `load()`'s catch (which maps via
 * `toAppError()` → `AppError.Auth`), OR explicitly check the result for a ResponseException with
 * 401/403 status and short-circuit to `Error(AppError.Auth())` before building `Loaded`. Other
 * (non-auth) endpoints may keep graceful degradation.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class DashboardAuthFailureSilentReproTest {
    private val json = Json { ignoreUnknownKeys = true }

    private val jsonHeaders = headersOf(
        HttpHeaders.ContentType, ContentType.Application.Json.toString(),
    )

    private val userJson = """{
        "id": "user-1",
        "email": "alice@example.com",
        "display_name": "Alice",
        "language": "ru",
        "timezone": "Europe/Moscow",
        "theme": "dark",
        "angular_unit": "deg_per_sec"
    }"""

    private val prsJson = """{"prs": []}"""
    private val diagnosticsJson = """{"user_id": "user-1", "findings": []}"""
    private val emptySessionsJson = """{"sessions": [], "total": 0}"""
    private val authErrorJson = """{"detail": "Not authenticated"}"""

    @Test
    fun usersMe401_mustSurfaceAuthError_notSilentLoaded_repro() = runTest {
        // /users/me → 401 Unauthorized (expired / stale token); other endpoints would also 401 in
        // reality, but the bug is observable from getMe alone since it is swallowed independently.
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/users/me" -> respond(authErrorJson, HttpStatusCode.Unauthorized, jsonHeaders)
                "/metrics/prs" -> respond(prsJson, HttpStatusCode.OK, jsonHeaders)
                "/metrics/diagnostics" -> respond(diagnosticsJson, HttpStatusCode.OK, jsonHeaders)
                "/sessions" -> respond(emptySessionsJson, HttpStatusCode.OK, jsonHeaders)
                else -> respond("""{"detail":"not found"}""", HttpStatusCode.NotFound, jsonHeaders)
            }
        }
        val httpClient = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
            expectSuccess = true
        }
        val viewModel = DashboardViewModel(
            sessionsApi = SessionsApi(httpClient),
            metricsApi = MetricsApi(httpClient),
            usersApi = UsersApi(httpClient),
            scope = this,
        )

        viewModel.uiState.test {
            // Initial Loading.
            assertIs<DashboardState.Loading>(awaitItem())
            viewModel.load()
            advanceUntilIdle()
            val finalState = awaitItem()

            // CONTRACT: an auth failure (401) MUST surface as Error(AppError.Auth), matching the
            // Sessions screen behavior, so the UI can route the user to re-login.
            val errorState = assertIs<DashboardState.Error>(finalState)
            assertIs<AppError.Auth>(errorState.error)
            // (No expect() on Loaded here — if the current code yields Loaded(user=null), the
            // assertIs<Error> above fails with a type mismatch → RED proving the silent-swallow bug.)
        }
    }
}
