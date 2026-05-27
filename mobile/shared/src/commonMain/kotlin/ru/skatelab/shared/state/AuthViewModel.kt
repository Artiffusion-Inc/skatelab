package ru.skatelab.shared.state

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.shared.api.UsersApi
import ru.skatelab.shared.auth.AuthRepository
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.utils.toAppError

sealed interface AuthUiState {
    data object Loading : AuthUiState
    data object LoggedOut : AuthUiState
    data class LoggedIn(val userId: String, val displayName: String?) : AuthUiState
    data class Error(val error: AppError) : AuthUiState
}

class AuthViewModel(
    private val authRepo: AuthRepository,
    private val usersApi: UsersApi,
) {
    private val _uiState = MutableStateFlow<AuthUiState>(AuthUiState.Loading)
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()

    suspend fun checkLogin() {
        if (authRepo.isLoggedIn()) {
            runCatching { usersApi.getMe() }
                .onSuccess { user -> _uiState.value = AuthUiState.LoggedIn(user.id, user.displayName) }
                .onFailure { _uiState.value = AuthUiState.LoggedIn("cached", null) }
        } else {
            _uiState.value = AuthUiState.LoggedOut
        }
    }

    suspend fun login(email: String, password: String) {
        _uiState.value = AuthUiState.Loading
        authRepo.login(email, password)
            .onSuccess {
                val user = runCatching { usersApi.getMe() }.getOrNull()
                _uiState.value = AuthUiState.LoggedIn(user?.id ?: "new", user?.displayName)
            }
            .onFailure { _uiState.value = AuthUiState.Error(it.toAppError()) }
    }

    suspend fun register(email: String, password: String, displayName: String) {
        _uiState.value = AuthUiState.Loading
        authRepo.register(email, password, displayName)
            .onSuccess {
                val user = runCatching { usersApi.getMe() }.getOrNull()
                _uiState.value = AuthUiState.LoggedIn(user?.id ?: "new", user?.displayName ?: displayName)
            }
            .onFailure { _uiState.value = AuthUiState.Error(it.toAppError()) }
    }

    suspend fun logout() {
        authRepo.logout()
        _uiState.value = AuthUiState.LoggedOut
    }
}
