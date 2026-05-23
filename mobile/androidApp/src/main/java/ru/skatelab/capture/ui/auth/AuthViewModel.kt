package ru.skatelab.capture.ui.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import ru.skatelab.shared.state.AuthUiState
import ru.skatelab.shared.state.AuthViewModel as SharedAuthViewModel

@HiltViewModel
class AuthViewModel
    @Inject
    constructor(
        private val sharedAuthViewModel: SharedAuthViewModel,
    ) : ViewModel() {
        val uiState: StateFlow<AuthUiState> =
            sharedAuthViewModel.uiState
                .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), AuthUiState.Loading)

        fun checkLogin() {
            viewModelScope.launch { sharedAuthViewModel.checkLogin() }
        }

        fun login(
            email: String,
            password: String,
        ) {
            viewModelScope.launch { sharedAuthViewModel.login(email, password) }
        }

        fun register(
            email: String,
            password: String,
            displayName: String,
        ) {
            viewModelScope.launch { sharedAuthViewModel.register(email, password, displayName) }
        }

        fun logout() {
            viewModelScope.launch { sharedAuthViewModel.logout() }
        }
    }
