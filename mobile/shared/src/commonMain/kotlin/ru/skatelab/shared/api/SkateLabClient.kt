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

    /**
     * The `Auth` plugin's config, captured during `install(Auth)`. Its `providers`
     * list holds the `BearerAuthProvider` whose in-memory token cache we must
     * invalidate on logout / account switch — the public Ktor API exposes the
     * providers only through this config instance, not via `plugin(Auth)`.
     */
    private lateinit var authConfig: AuthConfig

    val httpClient = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }

        install(Logging) {
            level = LogLevel.ALL
            logger = Logger.DEFAULT
        }

        defaultRequest { url(baseUrl) }

        install(Auth) {
            authConfig = this
            bearer {
                loadTokens {
                    val access = tokenStorage.getAccessToken() ?: return@loadTokens null
                    val refresh = tokenStorage.getRefreshToken() ?: return@loadTokens null
                    BearerTokens(access, refresh)
                }
                refreshTokens {
                    val refreshToken = oldTokens?.refreshToken ?: return@refreshTokens null
                    val result = runCatching {
                        client.post("auth/refresh") {
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
            // Retry only transient server-side timeouts, NOT generic IOException
            // (ConnectException/offline is NOT transient — retrying delays the
            // network-error surfacing to the UI by 30s+, which breaks #330 offline
            // detection). Let IOException propagate immediately so UploadWorker
            // sets NETWORK_ERROR and ProcessingScreen shows "No connection"/"Retry".
            retryOnExceptionIf { _, cause ->
                cause is SocketTimeoutException ||
                cause is HttpRequestTimeoutException
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
    val notifications = NotificationsApi(httpClient)
    val choreography = ChoreographyApi(httpClient)
    val programs = ProgramsApi(httpClient)

    /**
     * Clear the Ktor `Auth` plugin's in-memory bearer-token cache.
     *
     * The plugin caches the loaded token in memory (`BearerAuthProvider` →
     * `AuthTokenHolder.value`) and only reloads from storage once per process
     * lifetime. After logout or login as a different account, the cache holds a
     * stale token, so authorized requests reuse it and hit the wrong user.
     * Call this whenever the session owner changes so the next authorized
     * request forces `loadTokens` to re-read storage.
     */
    fun clearAuthCache() {
        authConfig.providers
            .filterIsInstance<BearerAuthProvider>()
            .forEach { it.clearToken() }
    }
}