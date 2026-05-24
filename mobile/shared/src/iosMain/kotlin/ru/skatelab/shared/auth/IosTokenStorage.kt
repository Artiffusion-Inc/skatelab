package ru.skatelab.shared.auth

import com.russhwolf.settings.KeychainSettings
import com.russhwolf.settings.Settings

@OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)
fun createIosSettings(): Settings {
    return try {
        KeychainSettings(service = "ru.skatelab.auth")
    } catch (e: Exception) {
        Settings()  // Fallback to in-memory MapSettings on Keychain failure
    }
}