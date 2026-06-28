package ru.skatelab.shared.state

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import app.cash.turbine.test
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.ProcessApi
import ru.skatelab.shared.models.AppError
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs

/**
 * Repro — `ProcessApi.stream` silently swallows a 401/auth-expiry mid-stream, so
 * `ProcessingViewModel` never reaches a terminal state and the UI is stuck in
 * `ProcessingUiState.Progress` forever (no auth routing, no re-login prompt).
 *
 * Bug chain (fresh origin/master, post #367 + #370):
 *
 *   - `ProcessApi.kt:56` — `response.expectSuccess().body()` (the guard added by
 *     #367) throws `ResponseException` on a non-2xx status. For a 401 (token
 *     expired mid-stream) this is exactly what should bubble up to the ViewModel
 *     so it can route to `Failed(AppError.Auth)` + `propagateIfAuth` → logout.
 *   - `ProcessApi.kt:86-90` — `catch (_: Exception) { retries++; if (retries >
 *     maxRetries) return@flow; delay(1000L * retries) }` catches that
 *     `ResponseException`, retries 3x (every retry is another 401 against the
 *     dead access token), then silently `return@flow` — the auth error is
 *     swallowed INSIDE the flow before the ViewModel's `startProcessing`
 *     `try/catch` (ProcessingViewModel.kt:25-31) ever sees it.
 *   - `ProcessingViewModel.kt:34-45` — `observeProgress`'s `processApi.stream
 *     (taskId).collect { ... }` returns with NO terminal event emitted (no
 *     COMPLETED/FAILED), so `_uiState` stays at the `Progress(0f, "Queuing...")`
 *     set in `startProcessing` before `observeProgress` was called. The UI is
 *     trapped in `Progress` with no recovery.
 *
 * Contrast: every OTHER API method surfaces auth via the ViewModel
 * `try/catch → toAppError → AppError.Auth → propagateIfAuth → logout`
 * (`ExceptionMapping.kt`: 401/403 → `AppError.Auth`). The `ProcessApi.stream`
 * internal catch-all intercepts the throw BEFORE the ViewModel catch can route
 * auth — so auth-expiry is broken SPECIFICALLY for the streaming endpoint, while
 * non-streaming endpoints handle it correctly.
 *
 * Distinct from #384 (P2): #384 is the CANCELLED `when`-branch gap in
 * `observeProgress` (a server-emitted `cancelled` event that the `when` drops);
 * THIS bug (P3) is the stream-layer catch-all that terminates the flow with no
 * event at all on a 401. Different layer, trigger, and symptom.
 *
 * End-to-end status: ACTIVE — token expiry during a long processing stream is a
 * real reachable scenario (a stream can run for minutes; the access token can
 * expire mid-stream). The user is left trapped in `Progress` with no re-login
 * prompt and no error.
 *
 * Repro: a REAL `ProcessApi` wired to a `MockEngine` that responds 200 to
 * `POST /process/queue` (so `startProcessing` enqueues and reaches the stream)
 * and 401 to `GET /process/{taskId}/stream`. After `startProcessing` returns
 * (the `stream` catch-all has retried-then-returned), assert the final `uiState`
 * is NOT `ProcessingUiState.Progress` (expect `Failed(AppError.Auth)`) and that
 * no `Failed(AppError.Auth)` was ever emitted (the auth error was swallowed
 * upstream). Today the state stays `Progress` → RED.
 *
 * Proposed fix: don't catch `ResponseException` in the `stream` catch-all — let
 * it propagate so `ProcessingViewModel.startProcessing`'s catch routes to
 * `Failed(AppError.Auth)` + `propagateIfAuth` → logout/re-login. Or surface a
 * terminal `FAILED` event on `maxRetries` exhausted instead of silent
 * `return@flow`. The catch-all should only retry transient NETWORK errors
 * (`IOException`/`SocketTimeoutException`), not auth failures.
 */
class ProcessingViewModelStreamAuthExpiryReproTest {

    private fun client(queueOk: Boolean = true, streamStatus: HttpStatusCode = HttpStatusCode.Unauthorized): HttpClient {
        val engine = MockEngine { request ->
            when {
                request.url.encodedPath.endsWith("/process/queue") && queueOk -> respond(
                    """{"task_id": "task-1", "status": "pending"}""",
                    status = HttpStatusCode.OK,
                    headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                )
                request.url.encodedPath.endsWith("/stream") -> respond(
                    """{"detail":"Unauthorized"}""",
                    status = streamStatus,
                    headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                )
                else -> respond(
                    """{"message":"not found"}""",
                    status = HttpStatusCode.NotFound,
                    headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                )
            }
        }
        return HttpClient(engine) {
            install(ContentNegotiation) { json(Json { ignoreUnknownKeys = true }) }
            defaultRequest { url("https://api.skatelab.ru/v1/") }
        }
    }

    @Test
    fun startProcessing_onStream401_routesToFailedAuth_notStuckInProgress_repro() = runTest {
        // REAL ProcessApi (not a fake) — the bug lives in ProcessApi.stream's catch-all.
        val api = ProcessApi(client())
        val viewModel = ProcessingViewModel(api)

        viewModel.uiState.test {
            assertEquals(ProcessingUiState.Idle, awaitItem())
            viewModel.startProcessing("video-key")
            // startProcessing sets Progress(0f, "Queuing...") before observeProgress.
            val queuing = awaitItem()
            assertIs<ProcessingUiState.Progress>(queuing)

            // The stream 401s; ProcessApi.stream's catch-all retries 3x (each a 401,
            // delays skipped under runTest virtual time) then silently return@flow.
            // observeProgress.collect returns with NO terminal event emitted. With the
            // bug, no further uiState is produced and awaitItem() hangs until the
            // Turbine scope is cancelled — so read the final state from uiState.value
            // after startProcessing returns, rather than awaiting another emission.
        }

        // startProcessing has returned (the stream flow completed silently). The
        // access token was expired (401 on every stream attempt) yet the UI is still
        // in Progress — the auth error was swallowed by ProcessApi.stream's
        // catch-all and never routed to Failed(AppError.Auth) / propagateIfAuth.
        val finalState = viewModel.uiState.value
        assertFalse(
            finalState is ProcessingUiState.Progress,
            "BUG (P3): ProcessApi.stream silently swallows a 401/auth-expiry mid-stream " +
                "(catch-all at ProcessApi.kt:86-90 retries 3x then return@flow), so " +
                "ProcessingViewModel.observeProgress.collect returns with NO terminal " +
                "event and the UI is stuck in ProcessingUiState.Progress forever — no " +
                "auth routing, no re-login prompt. Expected a terminal state " +
                "(Failed(AppError.Auth)) so propagateIfAuth can log the user out, but " +
                "got ${finalState::class.simpleName}.",
        )
        // Belt-and-braces: the auth error should have been routed as
        // Failed(AppError.Auth) (ExceptionMapping maps 401/403 → AppError.Auth).
        assertIs<ProcessingUiState.Failed>(
            finalState,
            "BUG (P3): expected the 401 stream to route to Failed(AppError.Auth) so " +
                "propagateIfAuth can log the user out, but the auth error was swallowed " +
                "inside ProcessApi.stream's catch-all and never reached the ViewModel.",
        )
        assertIs<AppError.Auth>(
            (finalState as ProcessingUiState.Failed).error,
            "BUG (P3): expected Failed(AppError.Auth) for a 401 stream, got " +
                "${(finalState as ProcessingUiState.Failed).error::class.simpleName}.",
        )
    }
}