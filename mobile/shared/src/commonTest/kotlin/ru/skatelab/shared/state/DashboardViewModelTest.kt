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
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.MetricsApi
import ru.skatelab.shared.api.SessionsApi
import ru.skatelab.shared.api.UsersApi
import ru.skatelab.shared.viewmodel.DashboardViewModel
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull

@OptIn(ExperimentalCoroutinesApi::class)
class DashboardViewModelTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
        expectSuccess = true
    }

    private val jsonHeaders = headersOf(
        HttpHeaders.ContentType, ContentType.Application.Json.toString()
    )

    // --- Sample JSON responses ---

    private val userJson = """{
        "id": "user-1",
        "email": "alice@example.com",
        "display_name": "Alice",
        "language": "ru",
        "timezone": "Europe/Moscow",
        "theme": "dark",
        "angular_unit": "deg_per_sec"
    }"""

    private val prsJson = """{
        "prs": [{
            "element_type": "flip",
            "metric_name": "airtime",
            "value": 0.72,
            "session_id": "sess-1"
        }]
    }"""

    private val diagnosticsJson = """{
        "user_id": "user-1",
        "findings": [{
            "severity": "warning",
            "element": "flip",
            "metric": "airtime",
            "message": "Airtime below target",
            "detail": "Target: 0.8s, actual: 0.72s"
        }]
    }"""

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

    private val recentSessionsJson = """{
        "sessions": [$sessionJson],
        "total": 1
    }"""

    private val weeklySessionsJson = """{
        "sessions": [$sessionJson],
        "total": 1
    }"""

    private val emptySessionsJson = """{
        "sessions": [],
        "total": 0
    }"""

    private val errorJson = """{"detail": "Internal Server Error"}"""

    // --- Helper: build engine that routes by URL path ---

    private fun routeEngine(
        usersMe: Pair<String, HttpStatusCode> = userJson to HttpStatusCode.OK,
        metricsPrs: Pair<String, HttpStatusCode> = prsJson to HttpStatusCode.OK,
        metricsDiagnostics: Pair<String, HttpStatusCode> = diagnosticsJson to HttpStatusCode.OK,
        sessions: Pair<String, HttpStatusCode> = recentSessionsJson to HttpStatusCode.OK,
        sessionsWeekly: Pair<String, HttpStatusCode>? = null,
    ) = MockEngine { request ->
        val path = request.url.encodedPath
        when {
            path == "/users/me" -> respond(usersMe.first, usersMe.second, jsonHeaders)
            path == "/metrics/prs" -> respond(metricsPrs.first, metricsPrs.second, jsonHeaders)
            path == "/metrics/diagnostics" -> respond(metricsDiagnostics.first, metricsDiagnostics.second, jsonHeaders)
            path == "/sessions" -> {
                val limit = request.url.parameters["limit"]?.toIntOrNull() ?: 20
                if (limit > 10) {
                    val resp = sessionsWeekly ?: sessions
                    respond(resp.first, resp.second, jsonHeaders)
                } else {
                    respond(sessions.first, sessions.second, jsonHeaders)
                }
            }
            else -> respond(errorJson, HttpStatusCode.NotFound, jsonHeaders)
        }
    }

    private fun TestScope.createViewModel(engine: MockEngine): DashboardViewModel {
        val httpClient = client(engine)
        return DashboardViewModel(
            sessionsApi = SessionsApi(httpClient),
            metricsApi = MetricsApi(httpClient),
            usersApi = UsersApi(httpClient),
            scope = this,
        )
    }

    // --- Tests ---

    @Test
    fun allEndpointsSucceed_showsLoadedWithAllData() = runTest {
        val engine = routeEngine()
        val viewModel = createViewModel(engine)

        viewModel.uiState.test {
            assertEquals(DashboardState.Loading, awaitItem())
            viewModel.load()
            advanceUntilIdle()
            val loaded = awaitItem()
            assertIs<DashboardState.Loaded>(loaded)
            assertEquals("user-1", loaded.data.user?.id)
            assertEquals("Alice", loaded.data.user?.displayName)
            assertEquals(1, loaded.data.personalRecords.size)
            assertEquals("flip", loaded.data.personalRecords[0].elementType)
            assertEquals(1, loaded.data.diagnostics.size)
            assertEquals("warning", loaded.data.diagnostics[0].severity)
            assertEquals(1, loaded.data.recentSessions.size)
            assertEquals("sess-1", loaded.data.recentSessions[0].id)
            assertEquals(1, loaded.data.weeklySessions.size)
            assertEquals("sess-1", loaded.data.weeklySessions[0].id)
        }
    }

    @Test
    fun usersApiFails_showsLoadedWithNullUserAndOtherData() = runTest {
        val engine = routeEngine(
            usersMe = errorJson to HttpStatusCode.InternalServerError,
        )
        val viewModel = createViewModel(engine)

        viewModel.uiState.test {
            assertEquals(DashboardState.Loading, awaitItem())
            viewModel.load()
            advanceUntilIdle()
            val loaded = awaitItem()
            assertIs<DashboardState.Loaded>(loaded)
            assertNull(loaded.data.user)
            assertEquals(1, loaded.data.personalRecords.size)
            assertEquals(1, loaded.data.diagnostics.size)
            assertEquals(1, loaded.data.recentSessions.size)
            assertEquals(1, loaded.data.weeklySessions.size)
        }
    }

    @Test
    fun allEndpointsFail_showsLoadedWithDefaults() = runTest {
        val engine = routeEngine(
            usersMe = errorJson to HttpStatusCode.InternalServerError,
            metricsPrs = errorJson to HttpStatusCode.InternalServerError,
            metricsDiagnostics = errorJson to HttpStatusCode.InternalServerError,
            sessions = errorJson to HttpStatusCode.InternalServerError,
        )
        val viewModel = createViewModel(engine)

        viewModel.uiState.test {
            assertEquals(DashboardState.Loading, awaitItem())
            viewModel.load()
            advanceUntilIdle()
            val loaded = awaitItem()
            assertIs<DashboardState.Loaded>(loaded)
            assertNull(loaded.data.user)
            assertEquals(0, loaded.data.personalRecords.size)
            assertEquals(0, loaded.data.diagnostics.size)
            assertEquals(0, loaded.data.recentSessions.size)
            assertEquals(0, loaded.data.weeklySessions.size)
        }
    }

    @Test
    fun emptyUser_noSessions_showsLoadedWithEmptyLists() = runTest {
        val engine = routeEngine(
            sessions = emptySessionsJson to HttpStatusCode.OK,
        )
        val viewModel = createViewModel(engine)

        viewModel.uiState.test {
            assertEquals(DashboardState.Loading, awaitItem())
            viewModel.load()
            advanceUntilIdle()
            val loaded = awaitItem()
            assertIs<DashboardState.Loaded>(loaded)
            assertEquals("user-1", loaded.data.user?.id)
            assertEquals(0, loaded.data.recentSessions.size)
            assertEquals(0, loaded.data.weeklySessions.size)
            assertEquals(1, loaded.data.personalRecords.size)
            assertEquals(1, loaded.data.diagnostics.size)
        }
    }
}