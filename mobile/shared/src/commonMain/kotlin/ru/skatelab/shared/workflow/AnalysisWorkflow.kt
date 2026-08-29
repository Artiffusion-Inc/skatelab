package ru.skatelab.shared.workflow

sealed interface AnalysisWorkflowState {
    data class Draft(val request: AnalysisRequest) : AnalysisWorkflowState

    data class Capture(val request: AnalysisRequest) : AnalysisWorkflowState

    data class Uploading(
        val request: AnalysisRequest,
        val video: CapturedVideo,
        val uploaded: UploadedVideo? = null,
    ) : AnalysisWorkflowState

    data class Queued(
        val request: ProcessRequest,
        val taskId: String? = null,
    ) : AnalysisWorkflowState

    data class Processing(
        val taskId: String,
        val sessionId: String,
        val progress: Float = 0f,
        val message: String = "",
    ) : AnalysisWorkflowState

    data class Completed(val sessionId: String) : AnalysisWorkflowState

    data class Failed(
        val work: RetryWork,
        val message: String,
        val retryCount: Int,
    ) : AnalysisWorkflowState

    data class Cancelled(val reason: String? = null) : AnalysisWorkflowState
}

sealed interface RetryWork {
    data class Capture(val request: AnalysisRequest) : RetryWork

    data class Upload(
        val request: AnalysisRequest,
        val video: CapturedVideo,
        val uploaded: UploadedVideo?,
    ) : RetryWork

    data class Queue(val request: ProcessRequest) : RetryWork

    data class Process(val taskId: String, val sessionId: String) : RetryWork

    data class Cancel(val taskId: String) : RetryWork
}

data class AnalysisWorkflow(
    val id: String,
    val state: AnalysisWorkflowState,
)
