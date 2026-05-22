package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class SessionUpdateRequest(
    @SerialName("element_type") val elementType: String? = null,
    val notes: String? = null,
)
