package ru.skatelab.shared.state

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.shared.api.SessionsApi
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.models.SessionListResponse

sealed interface SessionsUiState {
    data object Loading : SessionsUiState
    data class Loaded(val sessions: List<SessionResponse>, val total: Int, val page: Int) : SessionsUiState
    data class Error(val message: String) : SessionsUiState
}

class SessionsViewModel(private val sessionsApi: SessionsApi) {
    private val _uiState = MutableStateFlow<SessionsUiState>(SessionsUiState.Loading)
    val uiState: StateFlow<SessionsUiState> = _uiState.asStateFlow()

    private val _selectedSession = MutableStateFlow<SessionResponse?>(null)
    val selectedSession: StateFlow<SessionResponse?> = _selectedSession.asStateFlow()

    suspend fun loadSessions(page: Int = 1, limit: Int = 20) {
        _uiState.value = SessionsUiState.Loading
        try {
            val offset = (page - 1) * limit
            val response = sessionsApi.list(limit, offset)
            _uiState.value = SessionsUiState.Loaded(response.sessions, response.total, response.page)
        } catch (e: Exception) {
            _uiState.value = SessionsUiState.Error(e.message ?: "Failed to load sessions")
        }
    }

    suspend fun loadSession(id: String) {
        try {
            _selectedSession.value = sessionsApi.get(id)
        } catch (_: Exception) { }
    }
}
