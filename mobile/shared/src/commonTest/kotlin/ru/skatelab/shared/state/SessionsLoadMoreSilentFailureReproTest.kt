package ru.skatelab.shared.state

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
import ru.skatelab.shared.api.SessionsApi
import ru.skatelab.shared.models.AppError
import kotlin.test.Test
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * Repro for NEW bug — `SessionsViewModel.loadMore()` silently swallows pagination failures.
 *
 * Root cause: `SessionsViewModel.loadMore()` (SessionsViewModel.kt:65-67) catches ALL exceptions and
 * recovers by clearing only the loading flag, WITHOUT surfacing any error:
 *
 * ```kotlin
 * } catch (_: Exception) {
 *     _uiState.value = current.copy(isLoadingMore = false)   // ← silent: hasMore stays true,
 * }                                                          //   no error signal, list unchanged
 * ```
 *
 * Consequences:
 *  - `hasMore` stays `true` → the UI keeps offering "load more" / keeps triggering the
 *    scroll-to-bottom loadMore (SessionListScreen.kt:153), which keeps failing silently — an
 *    infinite retry loop the user cannot see or recover from.
 *  - No error / no retry affordance for pagination — the user scrolling for older sessions sees
 *    the spinner flash and vanish with nothing appended, and no explanation.
 *  - Inconsistent within the SAME ViewModel: `loadSessions()` (initial load) uses
 *    `catch (e) { Error(e.toAppError()) }` (SessionsViewModel.kt:44-46) → a 401 there surfaces as
 *    `SessionsUiState.Error(AppError.Auth)`. But `loadMore()` for the SAME 401 (token expires
 *    mid-scroll) is silently swallowed → an already-loaded list just stops growing with no auth
 *    signal and no re-login routing. The user thinks "no more sessions" when really they're logged
 *    out.
 *
 * This is a real user-facing failure mode for the same auth-expiry scenario as #334/#335: an
 * expired token during infinite-scroll pagination is masked as "end of list" instead of surfaced
 * as an auth error.
 *
 * Existing `SessionsViewModelTest` covers `loadMore` happy-path (`loadMore_appendsSessions`) and the
 * `hasMore=false` guard (`loadMore_doesNotCallWhenNoHasMore`) — but NOT the failure path, so the
 * silent-swallow never surfaces in CI.
 *
 * This repro pins the contract: a failed `loadMore()` must surface an auth-aware error signal (so
 * the UI can route to re-login) — NOT silently revert to the prior `Loaded` with `hasMore=true`.
 * RED now: the state after a failed loadMore is `Loaded(isLoadingMore=false, hasMore=true)` with no
 * error. After the fix — surfacing pagination failure (e.g. a `loadMoreError: AppError?` field on
 * `Loaded`, or transitioning to `Error(e.toAppError())` while preserving the loaded list) — GREEN.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class SessionsLoadMoreSilentFailureReproTest {
    private val json = Json { ignoreUnknownKeys = true }

    private val jsonHeaders = headersOf(
        HttpHeaders.ContentType, ContentType.Application.Json.toString(),
    )

    private val sessionJson = """{
        "id": "sess-1",
        "user_id": "user-1",
        "element_type": "flip",
        "video_url": "https://r2.example.com/video.mp4",
        "processed_video_url": null,
        "status": "completed",
        "overall_score": 8.5,
        "recommendations": ["Keep knees bent"],
        "metrics": [],
        "created_at": "2026-05-24T12:00:00Z"
    }"""

    private val firstPageJson = """{
        "sessions": [$sessionJson],
        "total": 2,
        "next_cursor": "cursor-1",
        "has_more": true
    }"""

    private val authErrorJson = """{"detail": "Not authenticated"}"""

    @Test
    fun loadMore_failure_mustSurfaceError_notSilentSwallow_repro() = runTest {
        var callCount = 0
        val engine = MockEngine { request ->
            callCount++
            if (callCount == 1) {
                // Initial load: OK, has more.
                respond(firstPageJson, HttpStatusCode.OK, jsonHeaders)
            } else {
                // Pagination call (loadMore): token expired mid-scroll → 401.
                respond(authErrorJson, HttpStatusCode.Unauthorized, jsonHeaders)
            }
        }
        val httpClient = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
            expectSuccess = true
        }
        val viewModel = SessionsViewModel(SessionsApi(httpClient))

        // Initial load — establishes Loaded(hasMore=true).
        viewModel.loadSessions()
        advanceUntilIdle()
        val first = assertIs<SessionsUiState.Loaded>(viewModel.uiState.value)
        assertTrue(first.hasMore)

        // Trigger pagination — which fails with 401 (token expired mid-scroll).
        viewModel.loadMore()
        advanceUntilIdle()

        // CONTRACT: a failed loadMore (401) must surface an auth-aware error signal — matching
        // loadSessions() behavior — so the UI can route the user to re-login instead of silently
        // showing "no more sessions" (hasMore stays true, infinite invisible retry loop).
        //
        // RED now: state is Loaded(isLoadingMore=false, hasMore=true) with NO error (Loaded carries
        // no appError), so the assertIs<Error> below fails on type mismatch (actual Loaded). After
        // the fix surfaces a loadMoreError / transitions to Error(AppError.Auth), this is GREEN.
        val finalState = viewModel.uiState.value
        val errorState = assertIs<SessionsUiState.Error>(finalState)
        assertIs<AppError.Auth>(errorState.error)
    }
}
