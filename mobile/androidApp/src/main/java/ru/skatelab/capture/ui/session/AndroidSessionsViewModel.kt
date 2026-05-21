package ru.skatelab.capture.ui.session

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import ru.skatelab.shared.api.SkateLabClient
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.state.SessionsUiState
import ru.skatelab.shared.state.SessionsViewModel

@HiltViewModel
class AndroidSessionsViewModel
    @Inject
    constructor(
        skateLabClient: SkateLabClient,
    ) : ViewModel() {
        private val shared = SessionsViewModel(skateLabClient.sessions)

        val uiState: StateFlow<SessionsUiState> = shared.uiState
        val selectedSession: StateFlow<SessionResponse?> = shared.selectedSession

        fun loadSessions(page: Int = 1, limit: Int = 20) {
            viewModelScope.launch { shared.loadSessions(page, limit) }
        }

        fun loadSession(id: String) {
            viewModelScope.launch { shared.loadSession(id) }
        }

        fun refresh() {
            viewModelScope.launch { shared.loadSessions() }
        }
    }