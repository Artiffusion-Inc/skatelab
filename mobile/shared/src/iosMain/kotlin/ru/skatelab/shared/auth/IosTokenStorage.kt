package ru.skatelab.shared.auth

import com.russhwolf.settings.KeychainSettings
import com.russhwolf.settings.Settings

fun createIosSettings(): Settings = KeychainSettings(service = "ru.skatelab.auth")