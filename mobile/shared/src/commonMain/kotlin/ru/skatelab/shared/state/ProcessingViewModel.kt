package ru.skatelab.shared.state

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.shared.api.IProcessApi
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.models.ProcessStatus
import ru.skatelab.shared.utils.toAppError

sealed interface ProcessingUiState {
    data object Idle : ProcessingUiState
    data class Progress(val percent: Float, val message: String) : ProcessingUiState
    data class Completed(val sessionId: String) : ProcessingUiState
    data class Failed(val error: AppError) : ProcessingUiState
}

class ProcessingViewModel(private val processApi: IProcessApi) {
    private val _uiState = MutableStateFlow<ProcessingUiState>(ProcessingUiState.Idle)
    val uiState: StateFlow<ProcessingUiState> = _uiState.asStateFlow()

    suspend fun startProcessing(videoKey: String, sessionId: String? = null) {
        _uiState.value = ProcessingUiState.Progress(0f, "Queuing...")
        try {
            val response = processApi.queue(videoKey, sessionId)
            observeProgress(response.taskId)
        } catch (e: Exception) {
            _uiState.value = ProcessingUiState.Failed(e.toAppError())
        }
    }

    private suspend fun observeProgress(taskId: String) {
        processApi.stream(taskId).collect { event ->
            when (event.parsedStatus) {
                ProcessStatus.RUNNING ->
                    _uiState.value = ProcessingUiState.Progress(event.progress, event.message)
                ProcessStatus.COMPLETED ->
                    _uiState.value = ProcessingUiState.Completed(event.sessionId ?: taskId)
                ProcessStatus.FAILED ->
                    _uiState.value = ProcessingUiState.Failed(AppError.Server())
                else -> {}
            }
        }
    }

    suspend fun cancelProcessing(taskId: String) {
        runCatching { processApi.cancel(taskId) }
            .onFailure { _uiState.value = ProcessingUiState.Failed(it.toAppError()) }
    }
}
