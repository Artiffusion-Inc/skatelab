package ru.skatelab.shared.state

import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.models.ConnectionResponse

sealed interface ConnectionsState {
    data object Loading : ConnectionsState

    data class Loaded(
        val connections: List<ConnectionResponse>,
        val pendingInvites: List<ConnectionResponse>,
    ) : ConnectionsState

    data class Error(val error: AppError) : ConnectionsState
}

typealias ConnectionsUiState = ConnectionsState
