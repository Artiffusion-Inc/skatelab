package ru.skatelab.capture.ui.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import ru.skatelab.shared.state.PasswordRecoveryUiState
import ru.skatelab.shared.state.PasswordRecoveryViewModel as SharedPasswordRecoveryViewModel

@HiltViewModel
class AndroidPasswordRecoveryViewModel
    @Inject
    constructor(
        private val shared: SharedPasswordRecoveryViewModel,
    ) : ViewModel() {
        val uiState: StateFlow<PasswordRecoveryUiState> =
            shared.uiState.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), PasswordRecoveryUiState.Idle)

        fun requestReset(email: String) {
            viewModelScope.launch { shared.requestReset(email) }
        }
    }
