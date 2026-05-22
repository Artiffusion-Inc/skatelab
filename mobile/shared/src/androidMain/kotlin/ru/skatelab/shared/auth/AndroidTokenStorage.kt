package ru.skatelab.shared.auth

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

actual class TokenStorage actual constructor() {
    private var prefs: SharedPreferences? = null

    fun init(context: Context) {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        prefs = EncryptedSharedPreferences.create(
            context,
            "skatelab_tokens",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    actual suspend fun getAccessToken(): String? = prefs?.getString("access_token", null)

    actual suspend fun getRefreshToken(): String? = prefs?.getString("refresh_token", null)

    actual suspend fun saveTokens(access: String, refresh: String) {
        prefs?.edit()
            ?.putString("access_token", access)
            ?.putString("refresh_token", refresh)
            ?.apply()
    }

    actual suspend fun clearTokens() {
        prefs?.edit()?.clear()?.apply()
    }
}
