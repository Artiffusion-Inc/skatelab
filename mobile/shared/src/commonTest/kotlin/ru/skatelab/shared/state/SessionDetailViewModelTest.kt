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
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.MetricsApi
import ru.skatelab.shared.api.SessionsApi
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.viewmodel.SessionDetailViewModel
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class SessionDetailViewModelTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
        expectSuccess = true
    }

    private val sessionJson = """{
        "id": "s1",
        "user_id": "u1",
        "element_type": "axel",
        "video_url": null,
        "processed_video_url": null,
        "status": "completed",
        "overall_score": 7.2,
        "recommendations": [],
        "metrics": [],
        "created_at": "2026-05-28T12:00:00Z",
        "pose_data": {"poses": [[[0.5,0.5,0.9]]], "fps": 30.0},
        "phases": {"takeoff": 10, "peak": 15, "landing": 20}
    }"""

    private val registryJson = """{
        "metrics": {
            "jump_height": {"name": "jump_height", "unit": "cm", "label_ru": "Высота прыжка"}
        }
    }"""

    private val jsonHeaders = headersOf(
        HttpHeaders.ContentType, ContentType.Application.Json.toString()
    )

    @Test
    fun load_success_showsLoadedWithSessionAndMetricDefs() = runTest {
        val engine = MockEngine { request ->
            when {
                request.url.encodedPath == "/sessions/s1" ->
                    respond(sessionJson, status = HttpStatusCode.OK, headers = jsonHeaders)
                request.url.encodedPath == "/metrics/registry" ->
                    respond(registryJson, status = HttpStatusCode.OK, headers = jsonHeaders)
                else -> respond("Not found", status = HttpStatusCode.NotFound)
            }
        }
        val httpClient = client(engine)
        val sessionsApi = SessionsApi(httpClient)
        val metricsApi = MetricsApi(httpClient)
        val scope = CoroutineScope(UnconfinedTestDispatcher())
        val viewModel = SessionDetailViewModel(sessionsApi, metricsApi, scope)

        viewModel.uiState.test {
            assertEquals(SessionDetailState.Loading, awaitItem())
            viewModel.load("s1")
            val loaded = awaitItem()
            assertIs<SessionDetailState.Loaded>(loaded)
            assertEquals("s1", loaded.session.id)
            assertEquals("axel", loaded.session.elementType)
            assertEquals(7.2f, loaded.session.overallScore)
            assertEquals(1, loaded.metricDefs.size)
            assertEquals("jump_height", loaded.metricDefs["jump_height"]!!.name)
            assertEquals("cm", loaded.metricDefs["jump_height"]!!.unit)
            assertEquals("Высота прыжка", loaded.metricDefs["jump_height"]!!.labelRu)
        }
    }

    @Test
    fun load_notFound_showsNotFoundError() = runTest {
        val engine = MockEngine { request ->
            respond(
                """{"detail": "Not Found"}""",
                status = HttpStatusCode.NotFound,
                headers = jsonHeaders,
            )
        }
        val httpClient = client(engine)
        val sessionsApi = SessionsApi(httpClient)
        val metricsApi = MetricsApi(httpClient)
        val scope = CoroutineScope(UnconfinedTestDispatcher())
        val viewModel = SessionDetailViewModel(sessionsApi, metricsApi, scope)

        viewModel.uiState.test {
            assertEquals(SessionDetailState.Loading, awaitItem())
            viewModel.load("missing-id")
            val error = awaitItem()
            assertIs<SessionDetailState.Error>(error)
            assertIs<AppError.NotFound>(error.error)
        }
    }

    @Test
    fun load_timeout_showsTimeoutError() = runTest {
        val engine = MockEngine { request ->
            throw io.ktor.client.plugins.HttpRequestTimeoutException(
                url = request.url.toString(),
                timeoutMillis = 30_000,
            )
        }
        val httpClient = client(engine)
        val sessionsApi = SessionsApi(httpClient)
        val metricsApi = MetricsApi(httpClient)
        val scope = CoroutineScope(UnconfinedTestDispatcher())
        val viewModel = SessionDetailViewModel(sessionsApi, metricsApi, scope)

        viewModel.uiState.test {
            assertEquals(SessionDetailState.Loading, awaitItem())
            viewModel.load("s1")
            val error = awaitItem()
            assertIs<SessionDetailState.Error>(error)
            assertIs<AppError.Timeout>(error.error)
        }
    }

    @Test
    fun toggleSkeleton_flipsFlagInLoadedState() = runTest {
        val engine = MockEngine { request ->
            when {
                request.url.encodedPath == "/sessions/s1" ->
                    respond(sessionJson, status = HttpStatusCode.OK, headers = jsonHeaders)
                request.url.encodedPath == "/metrics/registry" ->
                    respond(registryJson, status = HttpStatusCode.OK, headers = jsonHeaders)
                else -> respond("Not found", status = HttpStatusCode.NotFound)
            }
        }
        val httpClient = client(engine)
        val sessionsApi = SessionsApi(httpClient)
        val metricsApi = MetricsApi(httpClient)
        val scope = CoroutineScope(UnconfinedTestDispatcher())
        val viewModel = SessionDetailViewModel(sessionsApi, metricsApi, scope)

        viewModel.uiState.test {
            assertEquals(SessionDetailState.Loading, awaitItem())
            viewModel.load("s1")
            val loaded = awaitItem()
            assertIs<SessionDetailState.Loaded>(loaded)
            assertEquals(true, loaded.showSkeleton)

            viewModel.toggleSkeleton()
            val toggled = awaitItem()
            assertIs<SessionDetailState.Loaded>(toggled)
            assertEquals(false, toggled.showSkeleton)

            viewModel.toggleSkeleton()
            val toggledBack = awaitItem()
            assertIs<SessionDetailState.Loaded>(toggledBack)
            assertEquals(true, toggledBack.showSkeleton)
        }
    }
}