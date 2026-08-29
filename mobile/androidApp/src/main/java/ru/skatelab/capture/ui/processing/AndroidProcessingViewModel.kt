package ru.skatelab.capture.ui.processing

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.ExistingWorkPolicy
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.capture.data.db.PendingUploadEntity
import ru.skatelab.capture.upload.UploadScheduler
import ru.skatelab.shared.api.SkateLabClient
import ru.skatelab.shared.state.ProcessingUiState
import ru.skatelab.shared.state.ProcessingViewModel

sealed interface UploadPhase {
    data object Idle : UploadPhase

    data class UploadStatus(val entity: PendingUploadEntity) : UploadPhase

    data class ReadyForProcessing(val videoKey: String, val sessionId: String, val taskId: String? = null) : UploadPhase

    data class UploadFailed(val isNetworkError: Boolean) : UploadPhase
}

@HiltViewModel
class AndroidProcessingViewModel
    @Inject
    constructor(
        private val client: SkateLabClient,
        private val pendingUploadDao: PendingUploadDao,
        @ApplicationContext private val appContext: Context,
    ) : ViewModel() {
        private val shared = ProcessingViewModel(client.process)

        val processingState: StateFlow<ProcessingUiState> =
            shared.uiState
                .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), ProcessingUiState.Idle)

        private val _uploadPhase = MutableStateFlow<UploadPhase>(UploadPhase.Idle)
        val uploadPhase: StateFlow<UploadPhase> = _uploadPhase.asStateFlow()

        fun observeUpload(uploadId: String) {
            viewModelScope.launch {
                pendingUploadDao.getByIdFlow(uploadId).collect { entity ->
                    if (entity == null) {
                        _uploadPhase.value = UploadPhase.UploadFailed(false)
                        return@collect
                    }
                    when (entity.status) {
                        "PROCESSING" -> {
                            _uploadPhase.value = UploadPhase.UploadStatus(entity)
                            entity.sessionId?.let { sid ->
                                _uploadPhase.value = UploadPhase.ReadyForProcessing(entity.videoKey ?: "", sid, entity.processTaskId)
                            }
                        }
                        "COMPLETED" -> {
                            _uploadPhase.value = UploadPhase.UploadStatus(entity)
                            entity.sessionId?.let { sid ->
                                _uploadPhase.value = UploadPhase.ReadyForProcessing(entity.videoKey ?: "", sid, entity.processTaskId)
                            }
                        }
                        "FAILED" -> {
                            _uploadPhase.value = UploadPhase.UploadFailed(false)
                        }
                        "NETWORK_ERROR" -> {
                            _uploadPhase.value = UploadPhase.UploadFailed(true)
                        }
                        else -> {
                            _uploadPhase.value = UploadPhase.UploadStatus(entity)
                        }
                    }
                }
            }
        }

        fun startSseProcessing(
            videoKey: String,
            sessionId: String,
            taskId: String? = null,
        ) {
            viewModelScope.launch {
                if (taskId != null) {
                    shared.observeTask(taskId)
                } else {
                    shared.startProcessing(videoKey, sessionId)
                }
            }
        }

        fun retry(
            videoKey: String,
            sessionId: String? = null,
        ) {
            viewModelScope.launch { shared.startProcessing(videoKey, sessionId) }
        }

        fun retryUpload(uploadId: String) {
            viewModelScope.launch {
                pendingUploadDao.resetForRetry(uploadId)
                UploadScheduler.enqueue(appContext, uploadId, ExistingWorkPolicy.REPLACE)
            }
        }

        fun cancel() {
            viewModelScope.launch { shared.cancelProcessing() }
        }
    }
