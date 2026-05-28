package ru.skatelab.shared.viewmodel

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import ru.skatelab.shared.api.MetricsApi
import ru.skatelab.shared.api.SessionsApi
import ru.skatelab.shared.state.SessionDetailState
import ru.skatelab.shared.utils.toAppError

class SessionDetailViewModel(
    private val sessionsApi: SessionsApi,
    private val metricsApi: MetricsApi,
    private val scope: CoroutineScope,
) {
    private val _uiState = MutableStateFlow<SessionDetailState>(SessionDetailState.Loading)
    val uiState = _uiState.asStateFlow()

    fun load(sessionId: String) {
        scope.launch {
            _uiState.value = SessionDetailState.Loading
            try {
                val session = sessionsApi.get(sessionId)
                val registry = metricsApi.getRegistry()
                _uiState.value = SessionDetailState.Loaded(
                    session = session,
                    metricDefs = registry.metrics,
                )
            } catch (e: Exception) {
                _uiState.value = SessionDetailState.Error(e.toAppError())
            }
        }
    }

    fun toggleSkeleton() {
        val current = _uiState.value as? SessionDetailState.Loaded ?: return
        _uiState.value = current.copy(showSkeleton = !current.showSkeleton)
    }
}