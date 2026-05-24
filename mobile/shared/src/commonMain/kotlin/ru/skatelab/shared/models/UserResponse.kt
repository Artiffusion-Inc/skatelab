package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class UserResponse(
    val id: String,
    val email: String,
    @SerialName("display_name") val displayName: String? = null,
    @SerialName("avatar_url") val avatarUrl: String? = null,
    val bio: String? = null,
    @SerialName("height_cm") val heightCm: Double? = null,
    @SerialName("weight_kg") val weightKg: Double? = null,
    val language: String = "ru",
    val timezone: String = "UTC",
    val theme: String = "dark",
    @SerialName("onboarding_role") val onboardingRole: String? = null,
    @SerialName("angular_unit") val angularUnit: String = "deg_per_sec",
)
