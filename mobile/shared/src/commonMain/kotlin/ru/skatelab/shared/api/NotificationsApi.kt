package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.client.request.patch
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import ru.skatelab.shared.models.MarkAllNotificationsReadResponse
import ru.skatelab.shared.models.NotificationListResponse
import ru.skatelab.shared.models.NotificationResponse
import ru.skatelab.shared.models.UnreadCountResponse
import ru.skatelab.shared.utils.expectSuccess

class NotificationsApi(private val client: HttpClient) {
    suspend fun list(
        page: Int = 1,
        pageSize: Int = 20,
        unreadOnly: Boolean = false,
    ): NotificationListResponse =
        client.get("notifications") {
            parameter("page", page)
            parameter("page_size", pageSize)
            parameter("unread_only", unreadOnly)
        }.expectSuccess().body()

    suspend fun getUnreadCount(): UnreadCountResponse =
        client.get("notifications/unread-count").expectSuccess().body()

    suspend fun markRead(notificationId: String): NotificationResponse =
        client.post("notifications/$notificationId/read").expectSuccess().body()

    suspend fun markReadPatch(notificationId: String): NotificationResponse =
        client.patch("notifications/$notificationId/read").expectSuccess().body()

    suspend fun markAllRead(): MarkAllNotificationsReadResponse =
        client.post("notifications/read-all").expectSuccess().body()

    suspend fun markAllReadPatch(): MarkAllNotificationsReadResponse =
        client.patch("notifications/read-all").expectSuccess().body()
}
