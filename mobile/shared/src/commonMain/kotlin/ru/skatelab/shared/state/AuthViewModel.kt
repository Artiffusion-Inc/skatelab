package ru.skatelab.shared.state

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.shared.auth.AuthRepository

sealed interface AuthUiState {
    data object Loading : AuthUiState
    data object LoggedOut : AuthUiState
    data class LoggedIn(val userId: String, val displayName: String?) : AuthUiState
    data class Error(val message: String) : AuthUiState
}

class AuthViewModel(private val authRepo: AuthRepository) {
    private val _uiState = MutableStateFlow<AuthUiState>(AuthUiState.Loading)
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()

    suspend fun checkLogin() {
        _uiState.value = if (authRepo.isLoggedIn()) AuthUiState.LoggedIn("cached", null) else AuthUiState.LoggedOut
    }

    suspend fun login(email: String, password: String) {
        _uiState.value = AuthUiState.Loading
        authRepo.login(email, password)
            .onSuccess { _uiState.value = AuthUiState.LoggedIn("new", null) }
            .onFailure { _uiState.value = AuthUiState.Error(it.message ?: "Login failed") }
    }

    suspend fun register(email: String, password: String, displayName: String) {
        _uiState.value = AuthUiState.Loading
        authRepo.register(email, password, displayName)
            .onSuccess { _uiState.value = AuthUiState.LoggedIn("new", displayName) }
            .onFailure { _uiState.value = AuthUiState.Error(it.message ?: "Registration failed") }
    }

    suspend fun logout() {
        authRepo.logout()
        _uiState.value = AuthUiState.LoggedOut
    }
}
