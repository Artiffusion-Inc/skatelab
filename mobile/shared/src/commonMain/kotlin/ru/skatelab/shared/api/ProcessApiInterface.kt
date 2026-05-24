package ru.skatelab.shared.api

import kotlinx.coroutines.flow.Flow
import ru.skatelab.shared.models.ProcessEvent

interface IProcessApi {
    suspend fun queue(
        videoKey: String,
        sessionId: String? = null,
        personClickX: Float? = null,
        personClickY: Float? = null,
        frameSkip: Int = 1,
        tracking: String = "auto",
    ): QueueProcessResponse

    suspend fun status(taskId: String): TaskStatusResponse

    suspend fun cancel(taskId: String)

    fun stream(taskId: String): Flow<ProcessEvent>
}
