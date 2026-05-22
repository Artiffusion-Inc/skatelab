package ru.skatelab.shared.models

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
