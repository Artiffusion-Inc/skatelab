package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class MetricsApiTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    @Test
    fun getRegistry_returnsMetricsRegistry() = kotlinx.coroutines.test.runTest {
        val payload = """{
            "metrics": {
                "jump_height": {
                    "name": "jump_height",
                    "label_ru": "Высота прыжка",
                    "unit": "cm",
                    "format": "%.1f",
                    "direction": "higher_is_better",
                    "element_types": ["axel", "lutz", "flip"],
                    "ideal_range": {"min": 30.0, "max": 60.0}
                }
            }
        }"""
        val engine = MockEngine { request ->
            assertEquals(HttpMethod.Get, request.method)
            assertEquals("/metrics/registry", request.url.encodedPath)
            respond(
                payload,
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = MetricsApi(client(engine))
        val response = api.getRegistry()
        assertEquals(1, response.metrics.size)
        val metric = response.metrics["jump_height"]!!
        assertEquals("jump_height", metric.name)
        assertEquals("Высота прыжка", metric.labelRu)
        assertEquals("cm", metric.unit)
        assertEquals(listOf("axel", "lutz", "flip"), metric.elementTypes)
    }

    @Test
    fun getTrend_returnsTrendData() = kotlinx.coroutines.test.runTest {
        var capturedQuery: String? = null
        val payload = """{
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
        val engine = MockEngine { request ->
            capturedQuery = request.url.encodedQuery
            respond(
                payload,
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = MetricsApi(client(engine))
        val response = api.getTrend("jump_height", period = "30d")
        assertEquals("jump_height", response.metricName)
        assertEquals("axel", response.elementType)
        assertEquals(2, response.dataPoints.size)
        assertEquals("improving", response.trend)
        assertTrue(capturedQuery!!.contains("metric_name=jump_height"))
        assertTrue(capturedQuery!!.contains("period=30d"))
    }

    @Test
    fun getPersonalRecords_returnsPRs() = kotlinx.coroutines.test.runTest {
        val payload = """{
            "prs": [
                {"element_type": "axel", "metric_name": "jump_height", "value": 45.2, "session_id": "s1"},
                {"element_type": "lutz", "metric_name": "rotation_speed", "value": 720.0, "session_id": "s2"}
            ]
        }"""
        val engine = MockEngine { request ->
            assertEquals(HttpMethod.Get, request.method)
            assertEquals("/metrics/prs", request.url.encodedPath)
            respond(
                payload,
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = MetricsApi(client(engine))
        val response = api.getPersonalRecords()
        assertEquals(2, response.prs.size)
        assertEquals("axel", response.prs[0].elementType)
        assertEquals(45.2, response.prs[0].value)
    }

    @Test
    fun getDiagnostics_returnsFindings() = kotlinx.coroutines.test.runTest {
        var capturedQuery: String? = null
        val payload = """{
            "user_id": "u1",
            "findings": [
                {"severity": "warning", "element": "axel", "metric": "jump_height", "message": "Below reference range", "detail": "45.2cm vs 50cm target"}
            ]
        }"""
        val engine = MockEngine { request ->
            capturedQuery = request.url.encodedQuery
            respond(
                payload,
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = MetricsApi(client(engine))
        val response = api.getDiagnostics("sess-1")
        assertEquals("u1", response.userId)
        assertEquals(1, response.findings.size)
        assertEquals("warning", response.findings[0].severity)
        assertTrue(capturedQuery!!.contains("session_id=sess-1"))
    }

    @Test
    fun getSummary_returnsElementSummary() = kotlinx.coroutines.test.runTest {
        var capturedQuery: String? = null
        val payload = """{
            "element": "axel",
            "period": "30d",
            "trend": "improving",
            "findings": [{"severity": "info", "message": "On track"}],
            "metric_defs": {"jump_height": {"name": "jump_height", "unit": "cm"}},
            "personal_records": [{"metric_name": "jump_height", "value": 45.2, "session_id": "s1"}]
        }"""
        val engine = MockEngine { request ->
            capturedQuery = request.url.encodedQuery
            respond(
                payload,
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = MetricsApi(client(engine))
        val response = api.getSummary("axel", "30d")
        assertEquals("axel", response.element)
        assertEquals("30d", response.period)
        assertEquals("improving", response.trend)
        assertTrue(capturedQuery!!.contains("element_type=axel"))
        assertTrue(capturedQuery!!.contains("period=30d"))
    }
}