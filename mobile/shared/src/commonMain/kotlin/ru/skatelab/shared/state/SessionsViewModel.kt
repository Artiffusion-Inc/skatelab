package ru.skatelab.shared.state

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.shared.api.SessionsApi
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.models.SessionFilters
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.utils.toAppError

sealed interface SessionsUiState {
    data object Loading : SessionsUiState
    data class Loaded(
        val sessions: List<SessionResponse>,
        val total: Int,
        val nextCursor: String? = null,
        val hasMore: Boolean = false,
        val isLoadingMore: Boolean = false,
        val filters: SessionFilters = SessionFilters(),
    ) : SessionsUiState
    data class Error(val error: AppError) : SessionsUiState
}

class SessionsViewModel(private val sessionsApi: SessionsApi) {
    private val _uiState = MutableStateFlow<SessionsUiState>(SessionsUiState.Loading)
    val uiState: StateFlow<SessionsUiState> = _uiState.asStateFlow()

    private val _selectedSession = MutableStateFlow<SessionResponse?>(null)
    val selectedSession: StateFlow<SessionResponse?> = _selectedSession.asStateFlow()

    private var currentFilters = SessionFilters()
    private var currentLimit = 20

    /** Preserve the original element-only API used by existing mobile consumers. */
    suspend fun loadSessions(elementType: String? = null, limit: Int = 20) {
        loadSessions(SessionFilters(elementType = elementType), limit)
    }

    suspend fun loadSessions(filters: SessionFilters, limit: Int = 20) {
        currentFilters = filters
        currentLimit = limit
        _uiState.value = SessionsUiState.Loading
        try {
            val response = list(filters = filters, limit = limit, cursor = null)
            _uiState.value = SessionsUiState.Loaded(
                sessions = response.sessions,
                total = response.total,
                nextCursor = response.nextCursor,
                hasMore = response.hasMore,
                filters = filters,
            )
        } catch (e: Exception) {
            _uiState.value = SessionsUiState.Error(e.toAppError())
        }
    }

    suspend fun loadMore(limit: Int = currentLimit) {
        val current = _uiState.value as? SessionsUiState.Loaded ?: return
        if (!current.hasMore || current.isLoadingMore) return
        currentLimit = limit
        _uiState.value = current.copy(isLoadingMore = true)
        try {
            val response = list(
                filters = currentFilters,
                limit = limit,
                cursor = current.nextCursor,
            )
            _uiState.value = current.copy(
                sessions = current.sessions + response.sessions,
                total = response.total,
                nextCursor = response.nextCursor,
                hasMore = response.hasMore,
                isLoadingMore = false,
            )
        } catch (e: Exception) {
            // A failed page must be visible, especially when auth expires mid-scroll.
            _uiState.value = SessionsUiState.Error(e.toAppError())
        }
    }

    suspend fun loadSession(id: String) {
        _selectedSession.value = null
        _uiState.value = SessionsUiState.Loading
        try {
            _selectedSession.value = sessionsApi.get(id)
        } catch (e: Exception) {
            _uiState.value = SessionsUiState.Error(e.toAppError())
        }
    }

    suspend fun deleteSession(id: String) {
        try {
            sessionsApi.delete(id)
            removeDeletedSessions(setOf(id))
        } catch (e: Exception) {
            _uiState.value = SessionsUiState.Error(e.toAppError())
        }
    }

    suspend fun bulkDelete(ids: List<String>) {
        try {
            sessionsApi.bulkDelete(ids)
            removeDeletedSessions(ids.toSet())
        } catch (e: Exception) {
            // Do not optimistically remove rows: the backend rejects any foreign id atomically.
            _uiState.value = SessionsUiState.Error(e.toAppError())
        }
    }

    private suspend fun list(
        filters: SessionFilters,
        limit: Int,
        cursor: String?,
    ) = if (filters.userId == null) {
        // Keep the three-argument call path for existing API consumers and mocks.
        sessionsApi.list(limit = limit, cursor = cursor, elementType = filters.elementType)
    } else {
        sessionsApi.list(
            limit = limit,
            cursor = cursor,
            elementType = filters.elementType,
            userId = filters.userId,
        )
    }

    private fun removeDeletedSessions(ids: Set<String>) {
        val current = _uiState.value as? SessionsUiState.Loaded ?: return
        val normalizedIds = ids.map(String::trim).filter(String::isNotEmpty).toSet()
        val remaining = current.sessions.filterNot { it.id in normalizedIds }
        val removedCount = current.sessions.size - remaining.size
        if (removedCount == 0) return
        _uiState.value = current.copy(
            sessions = remaining,
            total = (current.total - removedCount).coerceAtLeast(0),
        )
        if (_selectedSession.value?.id in normalizedIds) {
            _selectedSession.value = null
        }
    }
}
