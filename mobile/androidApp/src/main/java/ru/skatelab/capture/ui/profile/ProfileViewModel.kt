package ru.skatelab.capture.ui.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import ru.skatelab.shared.api.SkateLabClient
import ru.skatelab.shared.models.UserResponse
import ru.skatelab.shared.state.AuthViewModel as SharedAuthViewModel

data class ProfileUiState(
    val isLoading: Boolean = true,
    val profile: UserResponse? = null,
    val error: String? = null,
    val isSaving: Boolean = false,
    val saveSuccess: Boolean = false,
)

@HiltViewModel
class ProfileViewModel
    @Inject
    constructor(
        private val client: SkateLabClient,
        private val sharedAuthViewModel: SharedAuthViewModel,
    ) : ViewModel() {
        private val usersApi = client.users

        private val _uiState = MutableStateFlow(ProfileUiState())
        val uiState: StateFlow<ProfileUiState> = _uiState.asStateFlow()

        private val _isLoggedOut = MutableStateFlow(false)
        val isLoggedOut: StateFlow<Boolean> = _isLoggedOut.asStateFlow()

        init {
            loadProfile()
        }

        fun loadProfile() {
            viewModelScope.launch {
                _uiState.value = _uiState.value.copy(isLoading = true, error = null)
                runCatching { usersApi.getMe() }
                    .onSuccess { user ->
                        _uiState.value =
                            _uiState.value.copy(
                                isLoading = false,
                                profile = user,
                                error = null,
                            )
                    }
                    .onFailure { e ->
                        _uiState.value =
                            _uiState.value.copy(
                                isLoading = false,
                                error = e.message ?: "Failed to load profile",
                            )
                    }
            }
        }

        fun updateProfile(
            displayName: String? = null,
            bio: String? = null,
            heightCm: Int? = null,
            weightKg: Double? = null,
        ) {
            viewModelScope.launch {
                _uiState.value = _uiState.value.copy(isSaving = true, saveSuccess = false)
                runCatching {
                    usersApi.updateProfile(displayName, bio, heightCm, weightKg)
                }
                    .onSuccess { user ->
                        _uiState.value =
                            _uiState.value.copy(
                                isSaving = false,
                                profile = user,
                                saveSuccess = true,
                            )
                    }
                    .onFailure { e ->
                        _uiState.value =
                            _uiState.value.copy(
                                isSaving = false,
                                error = e.message ?: "Failed to update profile",
                            )
                    }
            }
        }

        fun updateSettings(angularUnit: String) {
            viewModelScope.launch {
                _uiState.value = _uiState.value.copy(isSaving = true, saveSuccess = false)
                runCatching {
                    usersApi.updateSettings(angularUnit = angularUnit)
                }
                    .onSuccess { user ->
                        _uiState.value =
                            _uiState.value.copy(
                                isSaving = false,
                                profile = user,
                                saveSuccess = true,
                            )
                    }
                    .onFailure { e ->
                        _uiState.value =
                            _uiState.value.copy(
                                isSaving = false,
                                error = e.message ?: "Failed to update settings",
                            )
                    }
            }
        }

        fun logout() {
            viewModelScope.launch {
                sharedAuthViewModel.logout()
                _isLoggedOut.value = true
            }
        }

        fun clearError() {
            _uiState.value = _uiState.value.copy(error = null)
        }

        fun clearSaveSuccess() {
            _uiState.value = _uiState.value.copy(saveSuccess = false)
        }
    }
