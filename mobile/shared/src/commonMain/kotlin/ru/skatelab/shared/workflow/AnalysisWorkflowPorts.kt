package ru.skatelab.shared.workflow

import kotlinx.coroutines.flow.Flow

/** Platform adapters own camera and storage details; the workflow only sees opaque video data. */
interface VideoPort {
    suspend fun capture(workflowId: String, request: AnalysisRequest): CapturedVideo
}

interface SessionPort {
    suspend fun create(workflowId: String, request: SessionRequest): Session
}

interface UploadPort {
    suspend fun upload(workflowId: String, video: CapturedVideo): UploadedVideo
}

interface ProcessPort {
    /** Implementations must return the same task for a repeated [ProcessRequest.idempotencyKey]. */
    suspend fun queue(request: ProcessRequest): ProcessTask

    fun observe(taskId: String): Flow<ProcessUpdate>

    suspend fun cancel(taskId: String)
}

/** Storage is a host-owned seam; this package deliberately provides no persistence implementation. */
interface AnalysisWorkflowStore {
    suspend fun get(workflowId: String): AnalysisWorkflow?
    suspend fun save(workflow: AnalysisWorkflow)
    suspend fun pending(): List<AnalysisWorkflow>
}

data class AnalysisRequest(val elementType: String? = null)

data class SessionRequest(
    val videoKey: String,
    val elementType: String?,
)

data class CapturedVideo(val reference: String)

data class UploadedVideo(val key: String)

data class Session(val id: String)

data class ProcessRequest(
    val workflowId: String,
    val sessionId: String,
    val videoKey: String,
    val idempotencyKey: String,
)

data class ProcessTask(val taskId: String)

enum class ProcessUpdateStatus {
    RUNNING,
    COMPLETED,
    FAILED,
    CANCELLED,
}

data class ProcessUpdate(
    val status: ProcessUpdateStatus,
    val progress: Float = 0f,
    val message: String = "",
    val sessionId: String? = null,
    val error: String? = null,
)
