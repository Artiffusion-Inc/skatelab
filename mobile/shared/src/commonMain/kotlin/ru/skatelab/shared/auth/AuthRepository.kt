package ru.skatelab.shared.auth

import ru.skatelab.shared.api.AuthApi
import ru.skatelab.shared.models.TokenResponse

class AuthRepository(
    private val authApi: AuthApi,
    private val tokenStorage: TokenStorage,
) {
    suspend fun getAccessToken(): String? = tokenStorage.getAccessToken()

    suspend fun login(email: String, password: String): Result<Unit> = runCatching {
        val tokens = authApi.login(email, password)
        tokenStorage.saveTokens(tokens.accessToken, tokens.refreshToken)
    }

    suspend fun register(email: String, password: String, displayName: String): Result<Unit> = runCatching {
        val tokens = authApi.register(email, password, displayName)
        tokenStorage.saveTokens(tokens.accessToken, tokens.refreshToken)
    }

    suspend fun isLoggedIn(): Boolean = tokenStorage.getAccessToken() != null

    suspend fun logout() {
        tokenStorage.clearTokens()
    }

    suspend fun refreshIfNeeded(): String? {
        val refresh = tokenStorage.getRefreshToken() ?: return null
        return runCatching { authApi.refresh(refresh) }
            .getOrNull()
            ?.also { tokenStorage.saveTokens(it.accessToken, it.refreshToken) }
            ?.accessToken
    }
}
