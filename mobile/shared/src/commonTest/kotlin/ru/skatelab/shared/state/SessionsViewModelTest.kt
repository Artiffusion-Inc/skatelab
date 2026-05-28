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
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.SessionsApi
import ru.skatelab.shared.models.AppError
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull

class SessionsViewModelTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
        expectSuccess = true
    }

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

    private val sessionListJson = """{
        "sessions": [$sessionJson],
        "total": 1,
        "page": 1,
        "page_size": 20,
        "pages": 1
    }"""

    private val jsonHeaders = headersOf(
        HttpHeaders.ContentType, ContentType.Application.Json.toString()
    )

    @Test
    fun loadSessions_success_showsLoadedWithSessions() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            respond(sessionListJson, status = HttpStatusCode.OK, headers = jsonHeaders)
        }
        val api = SessionsApi(client(engine))
        val viewModel = SessionsViewModel(api)

        viewModel.uiState.test {
            assertEquals(SessionsUiState.Loading, awaitItem())
            viewModel.loadSessions()
            val loaded = awaitItem()
            assertIs<SessionsUiState.Loaded>(loaded)
            assertEquals(1, loaded.sessions.size)
            assertEquals("sess-1", loaded.sessions[0].id)
            assertEquals(1, loaded.total)
            assertEquals(1, loaded.page)
        }
    }

    @Test
    fun loadSessions_failure_showsErrorWithAppError() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            respond(
                """{"detail": "Internal Server Error"}""",
                status = HttpStatusCode.InternalServerError,
                headers = jsonHeaders,
            )
        }
        val api = SessionsApi(client(engine))
        val viewModel = SessionsViewModel(api)

        viewModel.uiState.test {
            assertEquals(SessionsUiState.Loading, awaitItem())
            viewModel.loadSessions()
            val error = awaitItem()
            assertIs<SessionsUiState.Error>(error)
            assertIs<AppError.Server>(error.error)
        }
    }

    @Test
    fun loadSession_success_setsSelectedSession() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            respond(sessionJson, status = HttpStatusCode.OK, headers = jsonHeaders)
        }
        val api = SessionsApi(client(engine))
        val viewModel = SessionsViewModel(api)

        assertNull(viewModel.selectedSession.value)

        viewModel.selectedSession.test {
            // Skip initial null
            awaitItem()
            viewModel.loadSession("sess-1")
            val session = awaitItem()
            assertEquals("sess-1", session?.id)
            assertEquals("flip", session?.elementType)
            assertEquals("completed", session?.status)
        }
    }

    @Test
    fun loadSession_failure_showsErrorWithAppError() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            respond(
                """{"detail": "Not Found"}""",
                status = HttpStatusCode.NotFound,
                headers = jsonHeaders,
            )
        }
        val api = SessionsApi(client(engine))
        val viewModel = SessionsViewModel(api)

        viewModel.uiState.test {
            assertEquals(SessionsUiState.Loading, awaitItem())
            viewModel.loadSession("missing-id")
            val error = awaitItem()
            assertIs<SessionsUiState.Error>(error)
            assertIs<AppError.NotFound>(error.error)
        }
    }

    @Test
    fun errorStateCarriesAppErrorNotString() {
        val state = SessionsUiState.Error(AppError.Network())
        assertIs<AppError.Network>((state as SessionsUiState.Error).error)
    }
}