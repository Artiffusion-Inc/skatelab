package ru.skatelab.shared.state

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.utils.toAppError

sealed interface PasswordRecoveryUiState {
    data object Idle : PasswordRecoveryUiState
    data object Loading : PasswordRecoveryUiState
    data object Sent : PasswordRecoveryUiState
    data class Error(val error: AppError) : PasswordRecoveryUiState
}

class PasswordRecoveryViewModel(
    private val api: AuthRecoveryApi,
) {
    private val _uiState = MutableStateFlow<PasswordRecoveryUiState>(PasswordRecoveryUiState.Idle)
    val uiState: StateFlow<PasswordRecoveryUiState> = _uiState.asStateFlow()

    suspend fun requestReset(email: String) {
        _uiState.value = PasswordRecoveryUiState.Loading
        runCatching { api.forgotPassword(email.trim()) }
            .onSuccess { _uiState.value = PasswordRecoveryUiState.Sent }
            .onFailure { _uiState.value = PasswordRecoveryUiState.Error(it.toAppError()) }
    }
}
