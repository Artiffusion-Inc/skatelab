package ru.skatelab.capture.presentation.export

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import ru.skatelab.capture.domain.repository.SessionRepository
import ru.skatelab.capture.domain.usecase.ExportSessionUseCase
import java.io.File
import javax.inject.Inject

@HiltViewModel
class ExportViewModel @Inject constructor(
    private val exportSessionUseCase: ExportSessionUseCase,
    private val sessionRepository: SessionRepository,
) : ViewModel() {

    private val _isExporting = MutableStateFlow(false)
    val isExporting: StateFlow<Boolean> = _isExporting

    private val _exportPath = MutableStateFlow<String?>(null)
    val exportPath: StateFlow<String?> = _exportPath

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error

    fun export(sessionId: String, outputDir: File) {
        viewModelScope.launch {
            _isExporting.value = true
            _error.value = null

            val session = sessionRepository.getSession(sessionId)
            if (session == null) {
                _error.value = "Session not found: $sessionId"
                _isExporting.value = false
                return@launch
            }

            val outputZip = File(outputDir, "${session.id}.zip")
            exportSessionUseCase.invoke(session, outputZip)
                .onSuccess { _exportPath.value = it.absolutePath }
                .onFailure { _error.value = it.message }

            _isExporting.value = false
        }
    }
}
