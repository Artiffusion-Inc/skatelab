package ru.skatelab.shared.state

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.shared.api.NotificationsApi
import ru.skatelab.shared.models.NotificationListResponse
import ru.skatelab.shared.utils.toAppError

class NotificationsViewModel(private val notificationsApi: NotificationsApi) {
    private val _uiState = MutableStateFlow<NotificationsUiState>(NotificationsUiState.Loading)
    val uiState: StateFlow<NotificationsUiState> = _uiState.asStateFlow()

    private val _unreadCount = MutableStateFlow(0)
    val unreadCount: StateFlow<Int> = _unreadCount.asStateFlow()

    private var currentPageSize = 20
    private var currentUnreadOnly = false

    suspend fun loadNotifications(pageSize: Int = 20, unreadOnly: Boolean = false) {
        currentPageSize = pageSize
        currentUnreadOnly = unreadOnly
        _uiState.value = NotificationsUiState.Loading
        try {
            val response = notificationsApi.list(
                page = 1,
                pageSize = pageSize,
                unreadOnly = unreadOnly,
            )
            setUnreadCount(response.unreadCount)
            _uiState.value = response.toLoaded()
        } catch (e: Exception) {
            _uiState.value = NotificationsUiState.Error(e.toAppError())
        }
    }

    suspend fun loadMore(pageSize: Int = currentPageSize) {
        val current = _uiState.value as? NotificationsUiState.Loaded ?: return
        if (!current.hasNext || current.isLoadingMore) return

        currentPageSize = pageSize
        _uiState.value = current.copy(isLoadingMore = true)
        try {
            val response = notificationsApi.list(
                page = current.page + 1,
                pageSize = pageSize,
                unreadOnly = currentUnreadOnly,
            )
            setUnreadCount(response.unreadCount)
            _uiState.value = current.copy(
                notifications = current.notifications + response.notifications,
                total = response.total,
                unreadCount = response.unreadCount,
                page = response.page,
                pageSize = response.pageSize,
                pages = response.pages,
                hasNext = response.hasNext,
                hasPrev = response.hasPrev,
                isLoadingMore = false,
            )
        } catch (e: Exception) {
            _uiState.value = NotificationsUiState.Error(e.toAppError())
        }
    }

    suspend fun loadUnreadCount() {
        try {
            val count = notificationsApi.getUnreadCount().unreadCount
            setUnreadCount(count)
            val current = _uiState.value as? NotificationsUiState.Loaded
            if (current != null) _uiState.value = current.copy(unreadCount = count)
        } catch (e: Exception) {
            _uiState.value = NotificationsUiState.Error(e.toAppError())
        }
    }

    suspend fun markRead(notificationId: String) {
        try {
            val marked = notificationsApi.markRead(notificationId)
            val current = _uiState.value as? NotificationsUiState.Loaded ?: return
            val existing = current.notifications.firstOrNull { it.id == notificationId }
            val becameRead = existing?.isRead == false && marked.isRead
            val updatedNotifications = if (currentUnreadOnly && marked.isRead) {
                current.notifications.filterNot { it.id == marked.id }
            } else {
                current.notifications.map { if (it.id == marked.id) marked else it }
            }
            val unread = if (becameRead) {
                (current.unreadCount - 1).coerceAtLeast(0)
            } else {
                current.unreadCount
            }
            setUnreadCount(
                if (becameRead) (_unreadCount.value - 1).coerceAtLeast(0) else _unreadCount.value,
            )
            _uiState.value = current.copy(
                notifications = updatedNotifications,
                total = if (currentUnreadOnly && becameRead) {
                    (current.total - 1).coerceAtLeast(0)
                } else {
                    current.total
                },
                unreadCount = unread,
            )
        } catch (e: Exception) {
            _uiState.value = NotificationsUiState.Error(e.toAppError())
        }
    }

    suspend fun markAllRead() {
        try {
            val result = notificationsApi.markAllRead()
            val current = _uiState.value as? NotificationsUiState.Loaded
            setUnreadCount(0)
            if (current != null) {
                val notifications = current.notifications.map { notification ->
                    if (notification.isRead) notification else notification.copy(isRead = true)
                }
                _uiState.value = current.copy(
                    notifications = if (currentUnreadOnly) emptyList() else notifications,
                    total = if (currentUnreadOnly) {
                        (current.total - result.markedRead).coerceAtLeast(0)
                    } else {
                        current.total
                    },
                    unreadCount = 0,
                )
            }
        } catch (e: Exception) {
            _uiState.value = NotificationsUiState.Error(e.toAppError())
        }
    }

    private fun setUnreadCount(count: Int) {
        _unreadCount.value = count.coerceAtLeast(0)
    }
}

private fun NotificationListResponse.toLoaded(): NotificationsUiState.Loaded =
    NotificationsUiState.Loaded(
        notifications = notifications,
        total = total,
        unreadCount = unreadCount,
        page = page,
        pageSize = pageSize,
        pages = pages,
        hasNext = hasNext,
        hasPrev = hasPrev,
    )
