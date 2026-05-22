package ru.skatelab.shared.auth

import com.russhwolf.settings.Settings

class TokenStorage(private val settings: Settings) {
    suspend fun getAccessToken(): String? = settings.getStringOrNull("access_token")
    suspend fun getRefreshToken(): String? = settings.getStringOrNull("refresh_token")
    suspend fun saveAccessToken(token: String) { settings.putString("access_token", token) }
    suspend fun saveRefreshToken(token: String) { settings.putString("refresh_token", token) }
    suspend fun saveTokens(access: String, refresh: String) {
        settings.putString("access_token", access)
        settings.putString("refresh_token", refresh)
    }
    suspend fun clearTokens() {
        settings.remove("access_token")
        settings.remove("refresh_token")
    }
}
