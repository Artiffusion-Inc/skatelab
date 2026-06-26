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
import ru.skatelab.shared.models.AppError
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
        // Auth failures (401/403) MUST propagate to load()'s catch so the UI surfaces
        // Error(AppError.Auth) and routes to re-login — they are NOT graceful-degradable.
        // Other failures (server fault, network, etc.) keep the existing empty-fallback.
        val userDeferred = async { runCatching { usersApi.getMe() }.onFailure { propagateIfAuth(it) } }
        val prsDeferred = async { runCatching { metricsApi.getPersonalRecords() }.onFailure { propagateIfAuth(it) } }
        val diagnosticsDeferred = async { runCatching { metricsApi.getDiagnostics() }.onFailure { propagateIfAuth(it) } }
        val recentDeferred = async { runCatching { sessionsApi.list(limit = 3) }.onFailure { propagateIfAuth(it) } }
        val weeklyDeferred = async { runCatching { sessionsApi.list(limit = 50) }.onFailure { propagateIfAuth(it) } }

        DashboardData(
            user = userDeferred.await().getOrDefault(null),
            personalRecords = prsDeferred.await().getOrElse { PRsResponse(emptyList()) }.prs,
            diagnostics = diagnosticsDeferred.await().getOrElse { DiagnosticsResponse("", emptyList()) }.findings,
            recentSessions = recentDeferred.await().getOrElse { SessionListResponse(emptyList(), 0) }.sessions,
            weeklySessions = weeklyDeferred.await().getOrElse { SessionListResponse(emptyList(), 0) }.sessions,
        )
    }

    private fun propagateIfAuth(throwable: Throwable) {
        if (throwable.toAppError() is AppError.Auth) throw throwable
    }
}