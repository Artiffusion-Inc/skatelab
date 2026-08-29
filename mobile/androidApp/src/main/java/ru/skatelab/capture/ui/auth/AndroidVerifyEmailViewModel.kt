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
import ru.skatelab.shared.state.VerifyEmailUiState
import ru.skatelab.shared.state.VerifyEmailViewModel as SharedVerifyEmailViewModel

@HiltViewModel
class AndroidVerifyEmailViewModel
    @Inject
    constructor(
        client: SkateLabClient,
    ) : ViewModel() {
        private val shared = SharedVerifyEmailViewModel(client.auth)

        val uiState: StateFlow<VerifyEmailUiState> =
            shared.uiState.stateIn(
                viewModelScope,
                SharingStarted.WhileSubscribed(5_000),
                VerifyEmailUiState.Idle,
            )

        fun verifyEmail(token: String) {
            viewModelScope.launch { shared.verifyEmail(token) }
        }

        fun resendVerification(email: String) {
            viewModelScope.launch { shared.resendVerification(email) }
        }
    }
