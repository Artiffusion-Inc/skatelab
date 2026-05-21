package ru.skatelab.shared.auth

import platform.Foundation.NSUserDefaults

actual class TokenStorage actual constructor() {
    private val defaults = NSUserDefaults.standardUserDefaults

    actual suspend fun getAccessToken(): String? =
        defaults.stringForKey("access_token")

    actual suspend fun getRefreshToken(): String? =
        defaults.stringForKey("refresh_token")

    actual suspend fun saveTokens(access: String, refresh: String) {
        defaults.setObject(access, forKey = "access_token")
        defaults.setObject(refresh, forKey = "refresh_token")
    }

    actual suspend fun clearTokens() {
        defaults.removeObjectForKey("access_token")
        defaults.removeObjectForKey("refresh_token")
    }
}
