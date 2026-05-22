package ru.skatelab.shared.auth

import io.ktor.client.plugins.api.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*

/**
 * Ktor client plugin that attaches a Bearer token to requests
 * and refreshes on 401 Unauthorized so subsequent requests use the new token.
 *
 * Install via:
 * ```
 * HttpClient(engine) {
 *     install(AuthInterceptor) {
 *         tokenStorage = myTokenStorage
 *         authRepository = myAuthRepository
 *     }
 * }
 * ```
 */
class AuthInterceptorConfig {
    lateinit var tokenStorage: TokenStorage
    lateinit var authRepository: AuthRepository
}

val AuthInterceptor = createClientPlugin("AuthInterceptor", ::AuthInterceptorConfig) {
    val storage = pluginConfig.tokenStorage
    val repo = pluginConfig.authRepository

    onRequest { request, _ ->
        val token = storage.getAccessToken()
        if (token != null) {
            request.header(HttpHeaders.Authorization, "Bearer $token")
        }
    }

    onResponse { response ->
        if (response.status == HttpStatusCode.Unauthorized) {
            repo.refreshIfNeeded()
            // Token is now refreshed — next request will pick it up.
        }
    }
}
