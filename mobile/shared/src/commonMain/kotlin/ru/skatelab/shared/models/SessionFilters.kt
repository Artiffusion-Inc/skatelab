package ru.skatelab.shared.models

/**
 * Session list selections used by the clients.
 *
 * The sessions endpoint currently supports only [userId] and [elementType]. The
 * remaining selections are kept here for client state and are intentionally not
 * sent as query parameters until the backend exposes matching filters.
 */
data class SessionFilters(
    val userId: String? = null,
    val elementType: String? = null,
    val status: String? = null,
    val dateFrom: String? = null,
    val dateTo: String? = null,
    val attempt: Int? = null,
    val season: String? = null,
)
