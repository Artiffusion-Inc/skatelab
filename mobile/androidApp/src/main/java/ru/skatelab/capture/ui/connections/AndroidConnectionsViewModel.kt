package ru.skatelab.capture.ui.connections

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import ru.skatelab.shared.state.ConnectionsState
import ru.skatelab.shared.state.ConnectionsViewModel as SharedConnectionsViewModel

@HiltViewModel
class AndroidConnectionsViewModel
    @Inject
    constructor(
        private val shared: SharedConnectionsViewModel,
    ) : ViewModel() {
        val uiState: StateFlow<ConnectionsState> =
            shared.uiState.stateIn(
                viewModelScope,
                SharingStarted.WhileSubscribed(5_000),
                ConnectionsState.Loading,
            )

        fun loadConnections() {
            viewModelScope.launch { shared.loadConnections() }
        }

        fun invite(
            toUserEmail: String,
            connectionType: String,
        ) {
            viewModelScope.launch { shared.invite(toUserEmail, connectionType) }
        }

        fun acceptInvite(connectionId: String) {
            viewModelScope.launch { shared.acceptInvite(connectionId) }
        }

        fun endConnection(connectionId: String) {
            viewModelScope.launch { shared.endConnection(connectionId) }
        }
    }
