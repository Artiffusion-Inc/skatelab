package ru.skatelab.capture.ui.session

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import ru.skatelab.shared.api.SkateLabClient
import ru.skatelab.shared.viewmodel.SessionDetailViewModel
import javax.inject.Inject

@HiltViewModel
class AndroidSessionDetailViewModel @Inject constructor(
    client: SkateLabClient,
) : ViewModel() {
    val shared = SessionDetailViewModel(
        sessionsApi = client.sessions,
        metricsApi = client.metrics,
        scope = viewModelScope,
    )
}