package ru.skatelab.capture.ui.processing

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.capture.data.db.PendingUploadEntity
import ru.skatelab.shared.api.SkateLabClient
import ru.skatelab.shared.state.ProcessingUiState
import ru.skatelab.shared.state.ProcessingViewModel

sealed interface UploadPhase {
    data object Idle : UploadPhase

    data class UploadStatus(val entity: PendingUploadEntity) : UploadPhase

    data class ReadyForProcessing(val videoKey: String, val sessionId: String) : UploadPhase

    data object UploadFailed : UploadPhase
}

@HiltViewModel
class AndroidProcessingViewModel
    @Inject
    constructor(
        private val client: SkateLabClient,
        private val pendingUploadDao: PendingUploadDao,
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
                        _uploadPhase.value = UploadPhase.UploadFailed
                        return@collect
                    }
                    _uploadPhase.value = UploadPhase.UploadStatus(entity)
                    when (entity.status) {
                        "PROCESSING" -> {
                            entity.sessionId?.let { sid ->
                                _uploadPhase.value = UploadPhase.ReadyForProcessing(entity.videoKey ?: "", sid)
                            }
                        }
                        "COMPLETED" -> {
                            entity.sessionId?.let { sid ->
                                _uploadPhase.value = UploadPhase.ReadyForProcessing(entity.videoKey ?: "", sid)
                            }
                        }
                        "FAILED" -> {
                            _uploadPhase.value = UploadPhase.UploadFailed
                        }
                    }
                }
            }
        }

        fun startSseProcessing(
            videoKey: String,
            sessionId: String,
        ) {
            viewModelScope.launch { shared.startProcessing(videoKey, sessionId) }
        }

        fun retry(
            videoKey: String,
            sessionId: String? = null,
        ) {
            viewModelScope.launch { shared.startProcessing(videoKey, sessionId) }
        }

        fun cancel() {
            viewModelScope.launch { shared.cancelProcessing() }
        }
    }
