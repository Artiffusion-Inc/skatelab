package ru.skatelab.shared.auth

import com.russhwolf.settings.KeychainSettings
import com.russhwolf.settings.Settings
import platform.Security.kSecAttrAccessible
import platform.Security.kSecAttrAccessibleAfterFirstUnlock
import platform.Security.kSecClass

fun createIosSettings(): Settings {
    return try {
        KeychainSettings(
            service = "ru.skatelab.auth",
            kSecClass to kSecClass,
            kSecAttrAccessible to kSecAttrAccessibleAfterFirstUnlock,
        )
    } catch (e: Exception) {
        Settings()  // Fallback to in-memory MapSettings on Keychain failure
    }
}
