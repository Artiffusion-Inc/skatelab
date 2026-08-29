package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import ru.skatelab.shared.models.GenerateTrainingPlanRequest
import ru.skatelab.shared.models.TrainingPlanResponse
import ru.skatelab.shared.utils.expectSuccess

class TrainingPlansApi(private val client: HttpClient) {
    suspend fun generate(request: GenerateTrainingPlanRequest): TrainingPlanResponse =
        client.post("training-plans/generate") {
            contentType(ContentType.Application.Json)
            setBody(request)
        }.expectSuccess().body()

    suspend fun get(planId: String): TrainingPlanResponse =
        client.get("training-plans/$planId").expectSuccess().body()
}
