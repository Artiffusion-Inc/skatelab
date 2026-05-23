package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

enum class ProcessStatus {
    RUNNING, COMPLETED, FAILED, CANCELLED,
    @Suppress("unused") UNKNOWN,
}

@Serializable
data class ProcessEvent(
    val progress: Float = 0f,
    val message: String = "",
    val status: String = "running",
    @SerialName("session_id") val sessionId: String? = null,
) {
    val parsedStatus: ProcessStatus
        get() = when (status) {
            "running" -> ProcessStatus.RUNNING
            "completed" -> ProcessStatus.COMPLETED
            "failed" -> ProcessStatus.FAILED
            "cancelled" -> ProcessStatus.CANCELLED
            else -> ProcessStatus.UNKNOWN
        }
}
