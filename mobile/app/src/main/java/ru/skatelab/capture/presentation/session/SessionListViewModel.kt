package ru.skatelab.capture.presentation.session

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.repository.SessionRepository

@HiltViewModel
class SessionListViewModel
    @Inject
    constructor(
        private val sessionRepository: SessionRepository,
    ) : ViewModel() {
        private val _sessions = MutableStateFlow<List<CaptureSession>>(emptyList())
        val sessions: StateFlow<List<CaptureSession>> = _sessions.asStateFlow()

        init {
            loadSessions()
        }

        fun loadSessions() {
            viewModelScope.launch {
                _sessions.value = sessionRepository.getSessions()
            }
        }

        fun deleteSession(id: String) {
            viewModelScope.launch {
                sessionRepository.deleteSession(id)
                loadSessions()
            }
        }
    }
