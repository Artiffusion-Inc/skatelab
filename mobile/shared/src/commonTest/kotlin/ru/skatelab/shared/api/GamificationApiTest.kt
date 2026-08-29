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
import ru.skatelab.shared.models.SkillProgressResponse
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

class GamificationApiTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    private val jsonHeaders = headersOf(
        HttpHeaders.ContentType,
        ContentType.Application.Json.toString(),
    )

    private val levelJson = """{
        "id":"level-1",
        "user_id":"user-1",
        "level":3,
        "total_xp":340,
        "xp_to_next":700,
        "title":"Спортсмен",
        "created_at":"2026-07-04T12:00:00Z",
        "updated_at":"2026-07-04T12:00:00Z"
    }"""

    private val skillJson = """{
        "id":"progress-1",
        "user_id":"user-1",
        "skill_id":"jumps_bronze",
        "category":"jumps",
        "tier":"bronze",
        "unlocked":true,
        "unlocked_at":"2026-07-04T12:00:00Z",
        "consecutive_sessions":4,
        "best_score":8.5,
        "xp_reward":50
    }"""

    @Test
    fun getUserLevel_usesExactRouteAndParsesAllFields() = runTest {
        var method: HttpMethod? = null
        var path: String? = null
        val engine = MockEngine { request ->
            method = request.method
            path = request.url.encodedPath
            respond(levelJson, HttpStatusCode.OK, jsonHeaders)
        }

        val response = GamificationApi(client(engine)).getUserLevel("user-1")

        assertEquals(HttpMethod.Get, method)
        assertEquals("/users/user-1/level", path)
        assertEquals("level-1", response.id)
        assertEquals("user-1", response.userId)
        assertEquals(3, response.level)
        assertEquals(340, response.totalXp)
        assertEquals(700, response.xpToNext)
        assertEquals("Спортсмен", response.title)
    }

    @Test
    fun getUserSkills_usesExactRouteAndParsesSkillProgress() = runTest {
        var path: String? = null
        val engine = MockEngine { request ->
            path = request.url.encodedPath
            respond("[$skillJson]", HttpStatusCode.OK, jsonHeaders)
        }

        val response = GamificationApi(client(engine)).getUserSkills("user-1")

        assertEquals("/users/user-1/skills", path)
        assertEquals(1, response.size)
        val skill = response.single()
        assertEquals("jumps_bronze", skill.skillId)
        assertEquals("jumps", skill.category)
        assertEquals("bronze", skill.tier)
        assertTrue(skill.unlocked)
        assertEquals(4, skill.consecutiveSessions)
        assertEquals(8.5, skill.bestScore)
        assertEquals(50, skill.xpReward)
    }

    @Test
    fun nonSuccess_isNotReturnedAsSuccess() = runTest {
        val engine = MockEngine {
            respond("{\"detail\":\"Unauthorized\"}", HttpStatusCode.Unauthorized, jsonHeaders)
        }

        val error = runCatching {
            GamificationApi(client(engine)).getUserLevel("user-1")
        }.exceptionOrNull()

        assertIs<io.ktor.client.plugins.ResponseException>(error)
    }

    @Test
    fun skillProgress_isSerializableWithBackendNames() {
        val encoded = json.encodeToString(SkillProgressResponse.serializer(), SkillProgressResponse(
            id = "progress-1",
            userId = "user-1",
            skillId = "jumps_bronze",
            category = "jumps",
            tier = "bronze",
            unlocked = false,
            unlockedAt = null,
            consecutiveSessions = 0,
            bestScore = 0.0,
            xpReward = 50,
        ))

        assertTrue(encoded.contains("\"user_id\":\"user-1\""))
        assertTrue(encoded.contains("\"skill_id\":\"jumps_bronze\""))
        assertTrue(encoded.contains("\"consecutive_sessions\":0"))
    }
}
