package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.get
import ru.skatelab.shared.models.SkillProgressResponse
import ru.skatelab.shared.models.UserLevelResponse
import ru.skatelab.shared.utils.expectSuccess

class GamificationApi(private val client: HttpClient) {
    suspend fun getUserLevel(userId: String): UserLevelResponse =
        client.get("users/$userId/level").expectSuccess().body()

    suspend fun getUserSkills(userId: String): List<SkillProgressResponse> =
        client.get("users/$userId/skills").expectSuccess().body()
}
