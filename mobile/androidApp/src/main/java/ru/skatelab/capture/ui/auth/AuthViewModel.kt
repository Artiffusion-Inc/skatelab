package ru.skatelab.capture.ui.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import ru.skatelab.shared.auth.AuthRepository
import ru.skatelab.shared.state.AuthUiState
import ru.skatelab.shared.state.AuthViewModel as SharedAuthViewModel

@HiltViewModel
class AuthViewModel @Inject constructor(
    private val authRepository: AuthRepository,
) : ViewModel() {

    private val shared = SharedAuthViewModel(authRepository)

    val uiState: StateFlow<AuthUiState> = shared.uiState
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), AuthUiState.Loading)

    fun checkLogin() {
        viewModelScope.launch { shared.checkLogin() }
    }

    fun login(email: String, password: String) {
        viewModelScope.launch { shared.login(email, password) }
    }

    fun register(email: String, password: String, displayName: String) {
        viewModelScope.launch { shared.register(email, password, displayName) }
    }

    fun logout() {
        viewModelScope.launch { shared.logout() }
    }
}
