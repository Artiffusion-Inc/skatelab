package ru.skatelab.capture.presentation.export

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import ru.skatelab.capture.domain.usecase.ExportSessionUseCase
import java.io.File
import javax.inject.Inject

@HiltViewModel
class ExportViewModel @Inject constructor(
    private val exportSessionUseCase: ExportSessionUseCase,
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
            // Will be wired up when SessionRepository provides real sessions
            _isExporting.value = false
        }
    }
}
