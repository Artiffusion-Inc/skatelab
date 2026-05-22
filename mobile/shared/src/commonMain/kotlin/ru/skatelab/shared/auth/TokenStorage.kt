package ru.skatelab.shared.auth

import com.russhwolf.settings.Settings

class TokenStorage(private val settings: Settings) {
    fun getAccessToken(): String? = settings.getStringOrNull("access_token")
    fun getRefreshToken(): String? = settings.getStringOrNull("refresh_token")
    fun saveAccessToken(token: String) { settings.putString("access_token", token) }
    fun saveRefreshToken(token: String) { settings.putString("refresh_token", token) }
    fun saveTokens(access: String, refresh: String) {
        settings.putString("access_token", access)
        settings.putString("refresh_token", refresh)
    }
    fun clearTokens() {
        settings.remove("access_token")
        settings.remove("refresh_token")
    }
}
