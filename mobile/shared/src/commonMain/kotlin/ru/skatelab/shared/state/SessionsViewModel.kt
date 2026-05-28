package ru.skatelab.shared.state

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.shared.api.SessionsApi
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.models.SessionListResponse
import ru.skatelab.shared.utils.toAppError

sealed interface SessionsUiState {
    data object Loading : SessionsUiState
    data class Loaded(
        val sessions: List<SessionResponse>,
        val total: Int,
        val nextCursor: String? = null,
        val hasMore: Boolean = false,
    ) : SessionsUiState
    data class Error(val error: AppError) : SessionsUiState
}

class SessionsViewModel(private val sessionsApi: SessionsApi) {
    private val _uiState = MutableStateFlow<SessionsUiState>(SessionsUiState.Loading)
    val uiState: StateFlow<SessionsUiState> = _uiState.asStateFlow()

    private val _selectedSession = MutableStateFlow<SessionResponse?>(null)
    val selectedSession: StateFlow<SessionResponse?> = _selectedSession.asStateFlow()

    private var currentElementType: String? = null

    suspend fun loadSessions(elementType: String? = null, limit: Int = 20) {
        currentElementType = elementType
        _uiState.value = SessionsUiState.Loading
        try {
            val response = sessionsApi.list(limit = limit, cursor = null, elementType = elementType)
            _uiState.value = SessionsUiState.Loaded(
                sessions = response.sessions,
                total = response.total,
                nextCursor = response.nextCursor,
                hasMore = response.hasMore,
            )
        } catch (e: Exception) {
            _uiState.value = SessionsUiState.Error(e.toAppError())
        }
    }

    suspend fun loadMore(limit: Int = 20) {
        val current = _uiState.value as? SessionsUiState.Loaded ?: return
        if (!current.hasMore) return
        try {
            val response = sessionsApi.list(
                limit = limit,
                cursor = current.nextCursor,
                elementType = currentElementType,
            )
            _uiState.value = current.copy(
                sessions = current.sessions + response.sessions,
                nextCursor = response.nextCursor,
                hasMore = response.hasMore,
            )
        } catch (_: Exception) {
            // Keep existing data on load-more failure
        }
    }

    suspend fun loadSession(id: String) {
        _uiState.value = SessionsUiState.Loading
        try {
            _selectedSession.value = sessionsApi.get(id)
        } catch (e: Exception) {
            _uiState.value = SessionsUiState.Error(e.toAppError())
        }
    }
}
