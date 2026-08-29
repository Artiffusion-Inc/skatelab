package ru.skatelab.shared.state

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.shared.api.ConnectionsApi
import ru.skatelab.shared.models.ConnectionResponse
import ru.skatelab.shared.models.InviteRequest
import ru.skatelab.shared.utils.toAppError

class ConnectionsViewModel(private val connectionsApi: ConnectionsApi) {
    private val _uiState = MutableStateFlow<ConnectionsState>(ConnectionsState.Loading)
    val uiState: StateFlow<ConnectionsState> = _uiState.asStateFlow()

    suspend fun loadConnections() {
        _uiState.value = ConnectionsState.Loading
        try {
            val connections = connectionsApi.list()
            val pending = connectionsApi.pending()
            _uiState.value = ConnectionsState.Loaded(
                connections = connections.connections,
                pendingInvites = pending.connections,
            )
        } catch (e: Exception) {
            _uiState.value = ConnectionsState.Error(e.toAppError())
        }
    }

    suspend fun invite(toUserEmail: String, connectionType: String) {
        try {
            val invited = connectionsApi.invite(InviteRequest(toUserEmail, connectionType))
            val current = _uiState.value as? ConnectionsState.Loaded
            _uiState.value = (current ?: ConnectionsState.Loaded(emptyList(), emptyList())).copy(
                connections = (current?.connections ?: emptyList()) + invited,
            )
        } catch (e: Exception) {
            _uiState.value = ConnectionsState.Error(e.toAppError())
        }
    }

    suspend fun acceptInvite(connectionId: String) {
        try {
            val accepted = connectionsApi.accept(connectionId)
            val current = _uiState.value as? ConnectionsState.Loaded
            _uiState.value = (current ?: ConnectionsState.Loaded(emptyList(), emptyList())).withUpdated(
                accepted,
            )
        } catch (e: Exception) {
            _uiState.value = ConnectionsState.Error(e.toAppError())
        }
    }

    suspend fun endConnection(connectionId: String) {
        try {
            val ended = connectionsApi.end(connectionId)
            val current = _uiState.value as? ConnectionsState.Loaded
            _uiState.value = (current ?: ConnectionsState.Loaded(emptyList(), emptyList())).withUpdated(
                ended,
            )
        } catch (e: Exception) {
            _uiState.value = ConnectionsState.Error(e.toAppError())
        }
    }
}

private fun ConnectionsState.Loaded.withUpdated(connection: ConnectionResponse) = copy(
    connections = connections.replace(connection),
    pendingInvites = pendingInvites.filterNot { it.id == connection.id },
)

private fun List<ConnectionResponse>.replace(connection: ConnectionResponse): List<ConnectionResponse> {
    val index = indexOfFirst { it.id == connection.id }
    return if (index < 0) this + connection else toMutableList().also { it[index] = connection }
}
