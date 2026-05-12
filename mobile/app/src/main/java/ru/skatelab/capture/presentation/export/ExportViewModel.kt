package ru.skatelab.capture.presentation.export

import android.content.Context
import android.net.Uri
import androidx.core.content.FileProvider
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import ru.skatelab.capture.domain.repository.SessionRepository
import ru.skatelab.capture.domain.usecase.ExportSessionUseCase
import java.io.File
import javax.inject.Inject

@HiltViewModel
class ExportViewModel @Inject constructor(
    private val exportSessionUseCase: ExportSessionUseCase,
    private val sessionRepository: SessionRepository,
    @ApplicationContext private val appContext: Context,
) : ViewModel() {

    private val _isExporting = MutableStateFlow(false)
    val isExporting: StateFlow<Boolean> = _isExporting.asStateFlow()

    private val _exportPath = MutableStateFlow<String?>(null)
    val exportPath: StateFlow<String?> = _exportPath.asStateFlow()

    private val _shareUri = MutableStateFlow<Uri?>(null)
    val shareUri: StateFlow<Uri?> = _shareUri.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    fun export(sessionId: String, outputDir: File) {
        viewModelScope.launch {
            _isExporting.value = true
            _error.value = null

            try {
                val session = sessionRepository.getSession(sessionId)
                if (session == null) {
                    _error.value = "Session not found: $sessionId"
                    return@launch
                }

                val outputZip = File(outputDir, "${session.id}.zip")
                exportSessionUseCase.invoke(session, outputZip)
                    .onSuccess {
                        _exportPath.value = it.absolutePath
                        _shareUri.value = FileProvider.getUriForFile(
                            appContext,
                            "${appContext.packageName}.fileprovider",
                            it,
                        )
                    }
                    .onFailure { _error.value = it.message }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _error.value = e.message ?: "Export failed"
            } finally {
                _isExporting.value = false
            }
        }
    }

    fun onShareComplete() {
        _shareUri.value = null
    }

    /** Re-trigger sharing by re-emitting the URI from the current export path. */
    fun onShareClicked() {
        val path = _exportPath.value ?: return
        val file = File(path)
        if (file.exists()) {
            _shareUri.value = FileProvider.getUriForFile(
                appContext,
                "${appContext.packageName}.fileprovider",
                file,
            )
        }
    }
}
