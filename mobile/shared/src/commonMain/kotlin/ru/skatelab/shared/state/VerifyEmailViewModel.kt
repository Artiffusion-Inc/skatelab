package ru.skatelab.shared.state

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.shared.api.AuthApi
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.utils.toAppError

sealed interface VerifyEmailUiState {
    data object Idle : VerifyEmailUiState
    data object Loading : VerifyEmailUiState
    data object Verified : VerifyEmailUiState
    data object Sent : VerifyEmailUiState
    data class Error(val error: AppError) : VerifyEmailUiState
}

class VerifyEmailViewModel(
    private val api: AuthApi,
) {
    private val _uiState = MutableStateFlow<VerifyEmailUiState>(VerifyEmailUiState.Idle)
    val uiState: StateFlow<VerifyEmailUiState> = _uiState.asStateFlow()

    suspend fun verifyEmail(token: String) {
        _uiState.value = VerifyEmailUiState.Loading
        runCatching { api.verifyEmail(token.trim()) }
            .onSuccess { _uiState.value = VerifyEmailUiState.Verified }
            .onFailure { _uiState.value = VerifyEmailUiState.Error(it.toAppError()) }
    }

    suspend fun resendVerification(email: String) {
        _uiState.value = VerifyEmailUiState.Loading
        runCatching { api.resendVerification(email.trim()) }
            .onSuccess { _uiState.value = VerifyEmailUiState.Sent }
            .onFailure { _uiState.value = VerifyEmailUiState.Error(it.toAppError()) }
    }
}
