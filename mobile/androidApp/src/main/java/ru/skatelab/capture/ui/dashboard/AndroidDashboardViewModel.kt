package ru.skatelab.capture.ui.dashboard

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import ru.skatelab.shared.api.SkateLabClient
import ru.skatelab.shared.viewmodel.DashboardViewModel
import javax.inject.Inject

@HiltViewModel
class AndroidDashboardViewModel @Inject constructor(
    client: SkateLabClient,
) : ViewModel() {
    val shared = DashboardViewModel(
        sessionsApi = client.sessions,
        metricsApi = client.metrics,
        usersApi = client.users,
        scope = viewModelScope,
    )

    init { shared.load() }
}