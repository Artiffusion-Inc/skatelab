package ru.skatelab.shared.state

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.shared.api.AuthApi
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.utils.toAppError

sealed interface NewPasswordUiState {
    data object Idle : NewPasswordUiState
    data object Loading : NewPasswordUiState
    data object Success : NewPasswordUiState
    data class Error(val error: AppError) : NewPasswordUiState
}

class NewPasswordViewModel(
    private val api: AuthApi,
) {
    private val _uiState = MutableStateFlow<NewPasswordUiState>(NewPasswordUiState.Idle)
    val uiState: StateFlow<NewPasswordUiState> = _uiState.asStateFlow()

    suspend fun resetPassword(token: String, newPassword: String) {
        _uiState.value = NewPasswordUiState.Loading
        runCatching { api.resetPassword(token.trim(), newPassword) }
            .onSuccess { _uiState.value = NewPasswordUiState.Success }
            .onFailure { _uiState.value = NewPasswordUiState.Error(it.toAppError()) }
    }
}
