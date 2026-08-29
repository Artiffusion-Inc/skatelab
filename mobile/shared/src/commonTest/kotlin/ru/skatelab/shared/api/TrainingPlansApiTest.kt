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
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import ru.skatelab.shared.models.GenerateTrainingPlanRequest
import kotlin.test.Test
import kotlin.test.assertEquals

class TrainingPlansApiTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    private val jsonHeaders = headersOf(
        HttpHeaders.ContentType,
        ContentType.Application.Json.toString(),
    )

    private val planJson = """{
        "id":"plan-1",
        "user_id":"user-1",
        "session_id":"session-1",
        "items":[{
            "id":"item-1",
            "priority":1,
            "label_ru":"Упражнение",
            "description_ru":"Три подхода",
            "completed":false
        }],
        "generated_at":"2026-07-04T12:00:00Z",
        "completed":false,
        "focus_subscore":"landing_control",
        "created_at":"2026-07-04T12:00:00Z",
        "updated_at":"2026-07-04T12:00:00Z"
    }"""

    @Test
    fun generateAndGet_useExpectedMethodsAndPaths() = runTest {
        val methods = mutableListOf<HttpMethod>()
        val paths = mutableListOf<String>()
        val engine = MockEngine { request ->
            methods += request.method
            paths += request.url.encodedPath
            respond(planJson, status = HttpStatusCode.OK, headers = jsonHeaders)
        }
        val api = TrainingPlansApi(client(engine))

        val generated = api.generate(GenerateTrainingPlanRequest("session-1"))
        val loaded = api.get("plan-1")

        assertEquals("plan-1", generated.id)
        assertEquals("Упражнение", generated.items.single().labelRu)
        assertEquals("landing_control", loaded.focusSubscore)
        assertEquals(listOf(HttpMethod.Post, HttpMethod.Get), methods)
        assertEquals(listOf("/training-plans/generate", "/training-plans/plan-1"), paths)
    }
}
