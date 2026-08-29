package ru.skatelab.shared.state

import app.cash.turbine.test
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.NotificationsApi
import ru.skatelab.shared.models.AppError
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class NotificationsViewModelTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    private val jsonHeaders = headersOf(
        HttpHeaders.ContentType,
        ContentType.Application.Json.toString(),
    )

    private fun notification(
        id: String,
        isRead: Boolean,
        readAt: String? = null,
    ) = """{
        "id": "$id",
        "user_id": "user-1",
        "event_type": "analysis.completed",
        "title": "Анализ готов",
        "body": "Ваш анализ завершён",
        "deep_link": "skatelab://session/$id",
        "payload": {"session_id": "$id"},
        "is_read": $isRead,
        "read_at": ${readAt?.let { "\"$it\"" } ?: "null"},
        "created_at": "2026-07-04T12:00:00Z"
    }"""

    @Test
    fun loadAndLoadMore_appendPagesAndExposeUnreadCount() = runTest {
        var callCount = 0
        val engine = MockEngine { request ->
            callCount++
            val response = if (callCount == 1) {
                """{
                    "notifications": [${notification("n1", false)}],
                    "total": 2,
                    "unread_count": 2,
                    "page": 1,
                    "page_size": 1,
                    "pages": 2,
                    "has_next": true,
                    "has_prev": false
                }"""
            } else {
                """{
                    "notifications": [${notification("n2", true, "2026-07-04T12:01:00Z")}],
                    "total": 2,
                    "unread_count": 2,
                    "page": 2,
                    "page_size": 1,
                    "pages": 2,
                    "has_next": false,
                    "has_prev": true
                }"""
            }
            respond(response, status = HttpStatusCode.OK, headers = jsonHeaders)
        }
        val viewModel = NotificationsViewModel(NotificationsApi(client(engine)))

        viewModel.uiState.test {
            assertEquals(NotificationsUiState.Loading, awaitItem())
            viewModel.loadNotifications(pageSize = 1)
            val first = awaitItem()
            assertIs<NotificationsUiState.Loaded>(first)
            assertEquals(listOf("n1"), first.notifications.map { it.id })
            assertEquals(2, first.unreadCount)
            assertEquals(2, viewModel.unreadCount.value)
            assertEquals(1, first.page)
            assertEquals(true, first.hasNext)

            viewModel.loadMore()
            val loading = awaitItem()
            assertIs<NotificationsUiState.Loaded>(loading)
            assertEquals(true, loading.isLoadingMore)
            val second = awaitItem()
            assertIs<NotificationsUiState.Loaded>(second)
            assertEquals(listOf("n1", "n2"), second.notifications.map { it.id })
            assertEquals(2, second.page)
            assertEquals(false, second.hasNext)
            assertEquals(false, second.isLoadingMore)
        }
    }

    @Test
    fun markRead_updatesNotificationAndUnreadCount() = runTest {
        var callCount = 0
        val engine = MockEngine { request ->
            callCount++
            val response = when (callCount) {
                1 -> """{
                    "notifications": [${notification("n1", false)}],
                    "total": 1,
                    "unread_count": 1
                }"""
                else -> notification("n1", true, "2026-07-04T12:02:00Z")
            }
            respond(response, status = HttpStatusCode.OK, headers = jsonHeaders)
        }
        val viewModel = NotificationsViewModel(NotificationsApi(client(engine)))

        viewModel.uiState.test {
            awaitItem()
            viewModel.loadNotifications()
            val loaded = awaitItem()
            assertIs<NotificationsUiState.Loaded>(loaded)
            viewModel.markRead("n1")
            val marked = awaitItem()
            assertIs<NotificationsUiState.Loaded>(marked)
            assertEquals(true, marked.notifications.single().isRead)
            assertEquals("2026-07-04T12:02:00Z", marked.notifications.single().readAt)
            assertEquals(0, marked.unreadCount)
            assertEquals(0, viewModel.unreadCount.value)
        }
    }

    @Test
    fun markAllRead_marksLoadedItemsAndClearsUnreadCount() = runTest {
        var callCount = 0
        val engine = MockEngine { request ->
            callCount++
            val response = if (callCount == 1) {
                """{
                    "notifications": [${notification("n1", false)}, ${notification("n2", true)}],
                    "total": 2,
                    "unread_count": 1
                }"""
            } else {
                """{"marked_read": 1}"""
            }
            respond(response, status = HttpStatusCode.OK, headers = jsonHeaders)
        }
        val viewModel = NotificationsViewModel(NotificationsApi(client(engine)))

        viewModel.uiState.test {
            awaitItem()
            viewModel.loadNotifications()
            awaitItem()
            viewModel.markAllRead()
            val marked = awaitItem()
            assertIs<NotificationsUiState.Loaded>(marked)
            assertEquals(listOf(true, true), marked.notifications.map { it.isRead })
            assertEquals(0, marked.unreadCount)
            assertEquals(0, viewModel.unreadCount.value)
        }
    }

    @Test
    fun load_failure_mapsToTypedAppError() = runTest {
        val engine = MockEngine {
            respond(
                """{"detail":"Internal Server Error"}""",
                status = HttpStatusCode.InternalServerError,
                headers = jsonHeaders,
            )
        }
        val viewModel = NotificationsViewModel(NotificationsApi(client(engine)))

        viewModel.uiState.test {
            awaitItem()
            viewModel.loadNotifications()
            val error = awaitItem()
            assertIs<NotificationsUiState.Error>(error)
            assertIs<AppError.Server>(error.error)
        }
    }
}
