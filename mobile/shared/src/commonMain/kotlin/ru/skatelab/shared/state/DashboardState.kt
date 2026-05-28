package ru.skatelab.shared.state

import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.models.DiagnosticsFinding
import ru.skatelab.shared.models.PersonalRecord
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.models.UserResponse

data class DashboardData(
    val user: UserResponse?,
    val personalRecords: List<PersonalRecord>,
    val diagnostics: List<DiagnosticsFinding>,
    val recentSessions: List<SessionResponse>,
    val weeklySessions: List<SessionResponse>,
)

sealed interface DashboardState {
    data object Loading : DashboardState
    data class Loaded(val data: DashboardData) : DashboardState
    data class Error(val error: AppError) : DashboardState
}