package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.engine.*
import io.ktor.client.plugins.*
import io.ktor.client.plugins.contentnegotiation.*
import io.ktor.serialization.kotlinx.json.*
import kotlinx.serialization.json.Json

class SkateLabClient(
    private val baseUrl: String,
    engine: HttpClientEngine,
) {
    val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
    }

    val httpClient = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }

        // Base URL applied to every request via defaultRequest
        defaultRequest {
            url(baseUrl)
        }
    }

    val auth = AuthApi(httpClient)
    val sessions = SessionsApi(httpClient)
    val users = UsersApi(httpClient)
    val uploads = UploadsApi(httpClient)
    val process = ProcessApi(httpClient)
}
