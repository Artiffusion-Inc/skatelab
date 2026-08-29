package ru.skatelab.capture.navigation

import java.net.URI

sealed interface NotificationDestination {
    data class Session(val sessionId: String) : NotificationDestination

    data class TrainingPlan(val planId: String) : NotificationDestination

    data class Export(val exportId: String) : NotificationDestination

    data object Unknown : NotificationDestination
}

/** Maps server notification links without allowing arbitrary routes or IDs. */
fun mapNotificationDeepLink(deepLink: String?): NotificationDestination {
    val uri =
        deepLink?.let { runCatching { URI(it) }.getOrNull() }
            ?: return NotificationDestination.Unknown
    if (uri.scheme != "skatelab") return NotificationDestination.Unknown

    val id =
        uri.path
            ?.split('/')
            ?.filter(String::isNotEmpty)
            ?.singleOrNull()
            ?.takeIf(String::isNotBlank)
            ?: return NotificationDestination.Unknown

    return when (uri.host) {
        "session" -> NotificationDestination.Session(id)
        "training" -> NotificationDestination.TrainingPlan(id)
        "exports" -> NotificationDestination.Export(id)
        else -> NotificationDestination.Unknown
    }
}

fun NotificationDestination.toExistingRoute(): Any? =
    when (this) {
        is NotificationDestination.Session -> ResultDetailRoute(sessionId)
        is NotificationDestination.TrainingPlan -> null
        is NotificationDestination.Export -> null
        NotificationDestination.Unknown -> null
    }
