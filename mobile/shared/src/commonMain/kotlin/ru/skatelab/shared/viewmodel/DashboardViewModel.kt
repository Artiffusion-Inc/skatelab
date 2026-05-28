package ru.skatelab.shared.viewmodel

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import ru.skatelab.shared.api.MetricsApi
import ru.skatelab.shared.api.SessionsApi
import ru.skatelab.shared.api.UsersApi
import ru.skatelab.shared.models.DiagnosticsResponse
import ru.skatelab.shared.models.PRsResponse
import ru.skatelab.shared.models.SessionListResponse
import ru.skatelab.shared.state.DashboardData
import ru.skatelab.shared.state.DashboardState
import ru.skatelab.shared.utils.toAppError

class DashboardViewModel(
    private val sessionsApi: SessionsApi,
    private val metricsApi: MetricsApi,
    private val usersApi: UsersApi,
    private val scope: CoroutineScope,
) {
    private val _uiState = MutableStateFlow<DashboardState>(DashboardState.Loading)
    val uiState = _uiState.asStateFlow()

    fun load() {
        scope.launch {
            _uiState.value = DashboardState.Loading
            try {
                val data = loadDashboardData()
                _uiState.value = DashboardState.Loaded(data)
            } catch (e: Exception) {
                _uiState.value = DashboardState.Error(e.toAppError())
            }
        }
    }

    private suspend fun loadDashboardData(): DashboardData = coroutineScope {
        val userDeferred = async { runCatching { usersApi.getMe() } }
        val prsDeferred = async { runCatching { metricsApi.getPersonalRecords() } }
        val diagnosticsDeferred = async { runCatching { metricsApi.getDiagnostics() } }
        val recentDeferred = async { runCatching { sessionsApi.list(limit = 3) } }
        val weeklyDeferred = async { runCatching { sessionsApi.list(limit = 50) } }

        DashboardData(
            user = userDeferred.await().getOrDefault(null),
            personalRecords = prsDeferred.await().getOrElse { PRsResponse(emptyList()) }.prs,
            diagnostics = diagnosticsDeferred.await().getOrElse { DiagnosticsResponse("", emptyList()) }.findings,
            recentSessions = recentDeferred.await().getOrElse { SessionListResponse(emptyList(), 0) }.sessions,
            weeklySessions = weeklyDeferred.await().getOrElse { SessionListResponse(emptyList(), 0) }.sessions,
        )
    }
}