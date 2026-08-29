package ru.skatelab.capture.ui.notifications

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import ru.skatelab.shared.state.NotificationsUiState
import ru.skatelab.shared.state.NotificationsViewModel as SharedNotificationsViewModel

@HiltViewModel
class AndroidNotificationsViewModel
    @Inject
    constructor(
        private val shared: SharedNotificationsViewModel,
    ) : ViewModel() {
        val uiState: StateFlow<NotificationsUiState> =
            shared.uiState.stateIn(
                viewModelScope,
                SharingStarted.WhileSubscribed(5_000),
                NotificationsUiState.Loading,
            )
        val unreadCount: StateFlow<Int> =
            shared.unreadCount.stateIn(
                viewModelScope,
                SharingStarted.WhileSubscribed(5_000),
                0,
            )

        fun loadNotifications(
            pageSize: Int = 20,
            unreadOnly: Boolean = false,
        ) {
            viewModelScope.launch { shared.loadNotifications(pageSize, unreadOnly) }
        }

        fun loadMore() {
            viewModelScope.launch { shared.loadMore() }
        }

        fun markRead(notificationId: String) {
            viewModelScope.launch { shared.markRead(notificationId) }
        }

        fun markAllRead() {
            viewModelScope.launch { shared.markAllRead() }
        }
    }
