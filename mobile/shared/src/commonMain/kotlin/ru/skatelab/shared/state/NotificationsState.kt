package ru.skatelab.shared.state

import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.models.NotificationResponse

sealed interface NotificationsUiState {
    data object Loading : NotificationsUiState

    data class Loaded(
        val notifications: List<NotificationResponse>,
        val total: Int,
        val unreadCount: Int,
        val page: Int = 1,
        val pageSize: Int = 20,
        val pages: Int = 1,
        val hasNext: Boolean = false,
        val hasPrev: Boolean = false,
        val isLoadingMore: Boolean = false,
    ) : NotificationsUiState

    data class Error(val error: AppError) : NotificationsUiState
}

typealias NotificationsState = NotificationsUiState
