package ru.skatelab.capture.ui.processing

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import ru.skatelab.shared.api.SkateLabClient
import ru.skatelab.shared.state.ProcessingUiState
import ru.skatelab.shared.state.ProcessingViewModel

@HiltViewModel
class AndroidProcessingViewModel @Inject constructor(
    private val client: SkateLabClient,
) : ViewModel() {

    private val shared = ProcessingViewModel(client.process)

    val uiState: StateFlow<ProcessingUiState> = shared.uiState
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), ProcessingUiState.Idle)

    fun startProcessing(videoKey: String, sessionId: String? = null) {
        viewModelScope.launch { shared.startProcessing(videoKey, sessionId) }
    }

    fun retry(videoKey: String, sessionId: String? = null) {
        viewModelScope.launch { shared.startProcessing(videoKey, sessionId) }
    }
}