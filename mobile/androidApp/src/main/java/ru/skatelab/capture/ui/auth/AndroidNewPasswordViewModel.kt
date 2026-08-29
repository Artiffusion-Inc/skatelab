package ru.skatelab.capture.ui.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import ru.skatelab.shared.api.SkateLabClient
import ru.skatelab.shared.state.NewPasswordUiState
import ru.skatelab.shared.state.NewPasswordViewModel as SharedNewPasswordViewModel

@HiltViewModel
class AndroidNewPasswordViewModel
    @Inject
    constructor(
        client: SkateLabClient,
    ) : ViewModel() {
        private val shared = SharedNewPasswordViewModel(client.auth)

        val uiState: StateFlow<NewPasswordUiState> =
            shared.uiState.stateIn(
                viewModelScope,
                SharingStarted.WhileSubscribed(5_000),
                NewPasswordUiState.Idle,
            )

        fun resetPassword(
            token: String,
            newPassword: String,
        ) {
            viewModelScope.launch { shared.resetPassword(token, newPassword) }
        }
    }
