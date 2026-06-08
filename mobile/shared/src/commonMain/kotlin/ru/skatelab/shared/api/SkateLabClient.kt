package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.engine.*
import io.ktor.client.network.sockets.SocketTimeoutException
import io.ktor.client.plugins.*
import io.ktor.client.plugins.auth.*
import io.ktor.client.plugins.auth.providers.*
import io.ktor.client.plugins.contentnegotiation.*
import io.ktor.client.plugins.logging.*
import io.ktor.client.request.*
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.*
import kotlinx.io.IOException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import ru.skatelab.shared.auth.TokenStorage
import ru.skatelab.shared.models.TokenResponse

class SkateLabClient(
    private val baseUrl: String,
    engine: HttpClientEngine,
    private val tokenStorage: TokenStorage,
) {
    var onAuthFailure: (() -> Unit)? = null

    val json = Json { ignoreUnknownKeys = true; isLenient = true }

    val httpClient = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }

        install(Logging) {
            level = LogLevel.ALL
            logger = Logger.DEFAULT
        }

        defaultRequest { url(baseUrl) }

        install(Auth) {
            bearer {
                loadTokens {
                    val access = tokenStorage.getAccessToken() ?: return@loadTokens null
                    val refresh = tokenStorage.getRefreshToken() ?: return@loadTokens null
                    BearerTokens(access, refresh)
                }
                refreshTokens {
                    val refreshToken = oldTokens?.refreshToken ?: return@refreshTokens null
                    val result = runCatching {
                        client.post("/auth/refresh") {
                            markAsRefreshTokenRequest()
                            contentType(ContentType.Application.Json)
                            setBody(buildJsonObject { put("refresh_token", refreshToken) })
                        }.body<TokenResponse>()
                    }
                    if (result.isSuccess) {
                        val response = result.getOrThrow()
                        tokenStorage.saveTokens(response.accessToken, response.refreshToken)
                        BearerTokens(response.accessToken, response.refreshToken)
                    } else {
                        tokenStorage.clearTokens()
                        onAuthFailure?.invoke()
                        null
                    }
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
            )
        }

        install(HttpTimeout) {
            connectTimeoutMillis = 10_000
            requestTimeoutMillis = 30_000
            socketTimeoutMillis = 15_000
        }
    }

    val auth = AuthApi(httpClient)
    val sessions = SessionsApi(httpClient)
    val users = UsersApi(httpClient)
    val uploads = UploadsApi(httpClient)
    val process = ProcessApi(httpClient)
    val metrics = MetricsApi(httpClient)
}