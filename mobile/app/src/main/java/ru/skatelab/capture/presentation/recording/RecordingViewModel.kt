package ru.skatelab.capture.presentation.recording

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import ru.skatelab.capture.domain.usecase.StartRecordingUseCase
import ru.skatelab.capture.domain.usecase.StopRecordingUseCase
import java.io.File
import javax.inject.Inject

@HiltViewModel
class RecordingViewModel @Inject constructor(
    private val startRecordingUseCase: StartRecordingUseCase,
    private val stopRecordingUseCase: StopRecordingUseCase,
) : ViewModel() {

    private val _isRecording = MutableStateFlow(false)
    val isRecording: StateFlow<Boolean> = _isRecording

    private val _durationMs = MutableStateFlow(0L)
    val durationMs: StateFlow<Long> = _durationMs

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error

    private val _sessionId = MutableStateFlow<String?>(null)
    val sessionId: StateFlow<String?> = _sessionId

    fun startRecording(outputDir: File) {
        viewModelScope.launch {
            startRecordingUseCase.invoke(outputDir)
                .onSuccess { _isRecording.value = true }
                .onFailure { _error.value = it.message }
        }
    }

    fun stopRecording() {
        viewModelScope.launch {
            stopRecordingUseCase.invoke()
                .onSuccess {
                    _isRecording.value = false
                    _sessionId.value = java.util.UUID.randomUUID().toString()
                }
                .onFailure { _error.value = it.message }
        }
    }
}
