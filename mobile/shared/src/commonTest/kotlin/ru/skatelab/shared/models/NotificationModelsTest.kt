package ru.skatelab.shared.models

import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class NotificationModelsTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun notificationResponse_deserializesActionPayload() {
        val payload = """{
            "id": "n1",
            "user_id": "u1",
            "event_type": "training.assigned",
            "title": "Новая тренировка",
            "body": "Откройте план",
            "deep_link": "skatelab://training/plan-1",
            "payload": {"training_plan_id": "plan-1", "session_count": 3},
            "is_read": false,
            "read_at": null,
            "created_at": "2026-07-04T12:00:00Z"
        }"""

        val notification = json.decodeFromString<NotificationResponse>(payload)

        assertEquals("n1", notification.id)
        assertEquals("u1", notification.userId)
        assertEquals("training.assigned", notification.eventType)
        assertEquals("skatelab://training/plan-1", notification.deepLink)
        val actionPayload = notification.payload!!
        assertEquals("plan-1", actionPayload["training_plan_id"].toString().trim('"'))
        assertEquals("3", actionPayload["session_count"].toString())
        assertEquals(false, notification.isRead)
        assertNull(notification.readAt)
    }

    @Test
    fun listResponse_usesDefaultsForOptionalPaginationMetadata() {
        val response = json.decodeFromString<NotificationListResponse>(
            """{"notifications": [], "total": 0, "unread_count": 0}""",
        )

        assertEquals(1, response.page)
        assertEquals(20, response.pageSize)
        assertEquals(1, response.pages)
        assertEquals(false, response.hasNext)
        assertEquals(false, response.hasPrev)
    }
}
