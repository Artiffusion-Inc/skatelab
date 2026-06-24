package ru.skatelab.shared.auth

import ru.skatelab.shared.api.AuthApi

class AuthRepository(
    private val authApi: AuthApi,
    private val tokenStorage: TokenStorage,
    private val clearAuthCache: () -> Unit = {},
) {
    suspend fun getAccessToken(): String? = tokenStorage.getAccessToken()

    suspend fun login(email: String, password: String): Result<Unit> = runCatching {
        val tokens = authApi.login(email, password)
        tokenStorage.saveTokens(tokens.accessToken, tokens.refreshToken)
        clearAuthCache()
    }

    suspend fun register(email: String, password: String, displayName: String): Result<Unit> = runCatching {
        val tokens = authApi.register(email, password, displayName)
        tokenStorage.saveTokens(tokens.accessToken, tokens.refreshToken)
        clearAuthCache()
    }

    suspend fun isLoggedIn(): Boolean = tokenStorage.getAccessToken() != null

    suspend fun logout() {
        val refreshToken = tokenStorage.getRefreshToken()
        if (refreshToken != null) {
            runCatching { authApi.logout(refreshToken) }
        }
        tokenStorage.clearTokens()
        clearAuthCache()
    }

    suspend fun verifyEmail(token: String): Result<Unit> = runCatching { authApi.verifyEmail(token) }

    suspend fun resendVerification(email: String): Result<Unit> = runCatching { authApi.resendVerification(email) }

    suspend fun forgotPassword(email: String): Result<Unit> = runCatching { authApi.forgotPassword(email) }

    suspend fun resetPassword(token: String, newPassword: String): Result<Unit> = runCatching { authApi.resetPassword(token, newPassword) }
}