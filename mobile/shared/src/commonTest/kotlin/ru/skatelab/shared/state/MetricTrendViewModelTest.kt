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
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.MetricsApi
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.viewmodel.MetricTrendViewModel
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

@OptIn(ExperimentalCoroutinesApi::class)
class MetricTrendViewModelTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
        expectSuccess = true
    }

    private val jsonHeaders = headersOf(
        HttpHeaders.ContentType, ContentType.Application.Json.toString()
    )

    private val trendJson = """{
        "metric_name": "jump_height",
        "element_type": "axel",
        "data_points": [
            {"session_id": "s1", "value": 45.2, "is_pr": true, "date": "2026-05-01"},
            {"session_id": "s2", "value": 42.0, "is_pr": false, "date": "2026-05-10"}
        ],
        "trend": "improving",
        "current_pr": 45.2,
        "reference_range": {"min": 30.0, "max": 60.0}
    }"""

    private val trendJson90d = """{
        "metric_name": "jump_height",
        "element_type": "axel",
        "data_points": [
            {"session_id": "s3", "value": 47.0, "is_pr": true, "date": "2026-03-01"},
            {"session_id": "s4", "value": 44.5, "is_pr": false, "date": "2026-04-15"},
            {"session_id": "s5", "value": 45.2, "is_pr": false, "date": "2026-05-01"}
        ],
        "trend": "stable",
        "current_pr": 47.0,
        "reference_range": {"min": 30.0, "max": 60.0}
    }"""

    private val registryJson = """{
        "metrics": {
            "jump_height": {"name": "jump_height", "unit": "cm", "label_ru": "Высота прыжка"}
        }
    }"""

    private val registryEmptyJson = """{
        "metrics": {}
    }"""

    @Test
    fun load_with30dPeriod_showsLoadedWithTrendAndMetricDef() = runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/metrics/trend" -> respond(trendJson, HttpStatusCode.OK, jsonHeaders)
                "/metrics/registry" -> respond(registryJson, HttpStatusCode.OK, jsonHeaders)
                else -> respond("Not found", HttpStatusCode.NotFound)
            }
        }
        val api = MetricsApi(client(engine))
        val viewModel = MetricTrendViewModel(api, CoroutineScope(UnconfinedTestDispatcher()))

        viewModel.uiState.test {
            assertEquals(TrendState.Loading, awaitItem())
            viewModel.load("jump_height", "axel")
            val loaded = awaitItem()
            assertIs<TrendState.Loaded>(loaded)
            assertEquals("jump_height", loaded.trend.metricName)
            assertEquals("axel", loaded.trend.elementType)
            assertEquals(2, loaded.trend.dataPoints.size)
            assertEquals("improving", loaded.trend.trend)
            assertEquals(45.2, loaded.trend.currentPr)
            assertEquals("jump_height", loaded.metricDef.name)
            assertEquals("cm", loaded.metricDef.unit)
            assertEquals("Высота прыжка", loaded.metricDef.labelRu)
        }
    }

    @Test
    fun changePeriod_to90d_showsLoadingThenLoadedWithNewData() = runTest {
        var trendCallCount = 0
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/metrics/trend" -> {
                    trendCallCount++
                    val body = if (trendCallCount == 1) trendJson else trendJson90d
                    respond(body, HttpStatusCode.OK, jsonHeaders)
                }
                "/metrics/registry" -> respond(registryJson, HttpStatusCode.OK, jsonHeaders)
                else -> respond("Not found", HttpStatusCode.NotFound)
            }
        }
        val api = MetricsApi(client(engine))
        val viewModel = MetricTrendViewModel(api, CoroutineScope(UnconfinedTestDispatcher()))

        viewModel.uiState.test {
            assertEquals(TrendState.Loading, awaitItem())
            viewModel.load("jump_height", "axel")
            val first = awaitItem()
            assertIs<TrendState.Loaded>(first)
            assertEquals(2, first.trend.dataPoints.size)
            assertEquals("improving", first.trend.trend)

            viewModel.changePeriod("jump_height", "axel", "90d")
            val loading = awaitItem()
            assertIs<TrendState.Loading>(loading)
            val second = awaitItem()
            assertIs<TrendState.Loaded>(second)
            assertEquals(3, second.trend.dataPoints.size)
            assertEquals("stable", second.trend.trend)
            assertEquals(47.0, second.trend.currentPr)
        }
    }

    @Test
    fun load_unknownMetric_showsError() = runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/metrics/trend" -> respond(trendJson, HttpStatusCode.OK, jsonHeaders)
                "/metrics/registry" -> respond(registryEmptyJson, HttpStatusCode.OK, jsonHeaders)
                else -> respond("Not found", HttpStatusCode.NotFound)
            }
        }
        val api = MetricsApi(client(engine))
        val viewModel = MetricTrendViewModel(api, CoroutineScope(UnconfinedTestDispatcher()))

        viewModel.uiState.test {
            assertEquals(TrendState.Loading, awaitItem())
            viewModel.load("unknown_metric", "axel")
            val error = awaitItem()
            assertIs<TrendState.Error>(error)
            assertIs<AppError.Unknown>(error.error)
        }
    }

    @Test
    fun load_serverError_showsServerError() = runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/metrics/trend" -> respond(
                    """{"detail": "Internal Server Error"}""",
                    HttpStatusCode.InternalServerError,
                    jsonHeaders,
                )
                "/metrics/registry" -> respond(registryJson, HttpStatusCode.OK, jsonHeaders)
                else -> respond("Not found", HttpStatusCode.NotFound)
            }
        }
        val api = MetricsApi(client(engine))
        val viewModel = MetricTrendViewModel(api, CoroutineScope(UnconfinedTestDispatcher()))

        viewModel.uiState.test {
            assertEquals(TrendState.Loading, awaitItem())
            viewModel.load("jump_height", "axel")
            val error = awaitItem()
            assertIs<TrendState.Error>(error)
            assertIs<AppError.Server>(error.error)
        }
    }
}
