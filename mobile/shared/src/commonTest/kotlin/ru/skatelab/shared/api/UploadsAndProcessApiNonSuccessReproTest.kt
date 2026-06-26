package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * Repro — `UploadsApi.complete` and `ProcessApi.cancel` do NOT check
 * `response.status.isSuccess()` and never throw on a non-2xx response, so a
 * caller treats a rejected upload-complete / process-cancel as SUCCEEDED.
 *
 * This is the same bug class as #352 (AuthApi.verifyEmail/resetPassword missing
 * status guard) — these two methods were also written without the
 * `expectSuccess()` guard that every other UploadsApi/ProcessApi/SessionsApi
 * method uses:
 *
 *   - `UploadsApi.complete` (UploadsApi.kt:17-22):
 *       client.post("uploads/complete") { ... setBody(UploadCompleteRequest(...)) }
 *       // NO .expectSuccess()  ← returns normally even on 403/500
 *   - `ProcessApi.cancel` (ProcessApi.kt:43-45):
 *       client.post("process/$taskId/cancel")
 *       // NO .expectSuccess()  ← returns normally even on 403/500
 *
 * Compare siblings in the SAME files that DO guard:
 *   - `UploadsApi.init` → `.expectSuccess().body()`
 *   - `UploadsApi.presign` → `.expectSuccess().body()`
 *   - `ProcessApi.queue` → `.expectSuccess().body()`
 *   - `ProcessApi.status` → `.expectSuccess().body()`
 *
 * Impact:
 *   - Backend `POST /uploads/complete` can return 403 (IDOR / wrong key — see
 *     #341) or 500 (S3 finalize failure). With no status check, `complete`
 *     returns normally → the mobile caller believes the upload finalized and
 *     moves on to processing — the session never has a valid uploaded video.
 *   - `POST /process/{id}/cancel` 403 (task belongs to another user — see #339)
 *     or 5xx → `cancel` returns normally → the UI shows "cancelled" though the
 *     job is still running.
 *
 * The existing mobile tests cover request serialization / happy paths only —
 * the non-2xx path for these two methods is never exercised, so the missing
 * guard never surfaces in CI.
 *
 * Repro: MockEngine responds 403 to `/uploads/complete` and `/process/{id}/cancel`;
 * assert each method throws. RED now: both return normally (no exception).
 * After the fix (add `.expectSuccess()` as siblings do) → throws.
 */

class UploadsAndProcessApiNonSuccessReproTest {
    private fun failingClient(): HttpClient {
        val engine = MockEngine { _ ->
            respond(
                """{"message":"Forbidden"}""",
                status = HttpStatusCode.Forbidden,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        return HttpClient(engine) {
            install(ContentNegotiation) { json(Json { ignoreUnknownKeys = true }) }
            defaultRequest { url("https://api.skatelab.ru/v1/") }
        }
    }

    @Test
    fun uploadsComplete_nonSuccess_mustThrow_notSilentSuccess_repro() = runTest {
        val api = UploadsApi(failingClient())

        var threw = false
        try {
            api.complete(uploadId = "up_123", key = "uploads/x/y.mp4", parts = emptyList())
        } catch (e: Exception) {
            threw = true
        }
        assertTrue(
            threw,
            "BUG: UploadsApi.complete did NOT throw on a 403 response — the caller " +
                "treats a rejected upload-finalization as SUCCEEDED and moves on to " +
                "processing a session with no valid uploaded video. Siblings init/presign " +
                "use .expectSuccess(); complete does not.",
        )
    }

    @Test
    fun processCancel_nonSuccess_mustThrow_notSilentSuccess_repro() = runTest {
        val api = ProcessApi(failingClient())

        var threw = false
        try {
            api.cancel("proc_123")
        } catch (e: Exception) {
            threw = true
        }
        assertTrue(
            threw,
            "BUG: ProcessApi.cancel did NOT throw on a 403 response — the UI shows " +
                "'cancelled' though the job is still running (backend rejected cancel, " +
                "e.g. task belongs to another user — #339). Siblings queue/status use " +
                ".expectSuccess(); cancel does not.",
        )
    }
}