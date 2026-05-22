package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.engine.*
import io.ktor.client.network.sockets.SocketTimeoutException
import io.ktor.client.plugins.*
import io.ktor.client.plugins.auth.*
import io.ktor.client.plugins.auth.providers.*
import io.ktor.client.plugins.contentnegotiation.*
import io.ktor.client.plugins.sse.*
import io.ktor.client.request.*
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.*
import kotlinx.io.IOException
import kotlinx.serialization.json.Json
import ru.skatelab.shared.auth.TokenStorage
import ru.skatelab.shared.models.TokenResponse

class SkateLabClient(
    private val baseUrl: String,
    engine: HttpClientEngine,
    private val tokenStorage: TokenStorage,
) {
    val json = Json { ignoreUnknownKeys = true; isLenient = true }

    val httpClient = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }

        defaultRequest { url(baseUrl) }

        install(Auth) {
            bearer {
                cacheTokens = false
                loadTokens {
                    val access = tokenStorage.getAccessToken() ?: return@loadTokens null
                    val refresh = tokenStorage.getRefreshToken() ?: return@loadTokens null
                    BearerTokens(access, refresh)
                }
                refreshTokens {
                    val refreshToken = oldTokens?.refreshToken ?: return@refreshTokens null
                    runCatching {
                        client.post("/auth/refresh") {
                            markAsRefreshTokenRequest()
                            contentType(ContentType.Application.Json)
                            setBody(mapOf("refresh_token" to refreshToken))
                        }.body<TokenResponse>()
                    }.onSuccess { response ->
                        tokenStorage.saveTokens(response.accessToken, response.refreshToken)
                    }.onFailure {
                        tokenStorage.clearTokens()
                    }.getOrNull()?.let { BearerTokens(it.accessToken, it.refreshToken) }
                }
            }
        }

        install(HttpRequestRetry) {
            maxRetries = 3
            retryIf { _, response -> response.status.value.let { it >= 500 || it == 429 } }
            retryOnExceptionIf { _, cause ->
                cause is SocketTimeoutException ||
                cause is HttpRequestTimeoutException ||
                cause is IOException
            }
            exponentialDelay(
                base = 2.0,
                baseDelayMs = 500,
                maxDelayMs = 8_000,
                randomizationMs = 500,
                respectRetryAfter = true,
            )
        }

        install(HttpTimeout) {
            connectTimeoutMillis = 10_000
            requestTimeoutMillis = 30_000
            socketTimeoutMillis = 15_000
        }

        install(SSE) {
            reconnectionTime = 5000
            maxReconnectionAttempts = 3
        }
    }

    val auth = AuthApi(httpClient)
    val sessions = SessionsApi(httpClient)
    val users = UsersApi(httpClient)
    val uploads = UploadsApi(httpClient)
    val process = ProcessApi(httpClient)
    val metrics = MetricsApi(httpClient)
}
