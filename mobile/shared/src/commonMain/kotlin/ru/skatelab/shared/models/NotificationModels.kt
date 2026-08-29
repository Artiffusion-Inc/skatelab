package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

@Serializable
data class NotificationResponse(
    val id: String,
    @SerialName("user_id") val userId: String,
    @SerialName("event_type") val eventType: String,
    val title: String,
    val body: String,
    @SerialName("deep_link") val deepLink: String? = null,
    val payload: JsonObject? = null,
    @SerialName("is_read") val isRead: Boolean = false,
    @SerialName("read_at") val readAt: String? = null,
    @SerialName("created_at") val createdAt: String,
)

@Serializable
data class NotificationListResponse(
    val notifications: List<NotificationResponse>,
    val total: Int,
    @SerialName("unread_count") val unreadCount: Int,
    val page: Int = 1,
    @SerialName("page_size") val pageSize: Int = 20,
    val pages: Int = 1,
    @SerialName("has_next") val hasNext: Boolean = false,
    @SerialName("has_prev") val hasPrev: Boolean = false,
)

@Serializable
data class UnreadCountResponse(
    @SerialName("unread_count") val unreadCount: Int,
)

@Serializable
data class MarkAllNotificationsReadResponse(
    @SerialName("marked_read") val markedRead: Int,
)
