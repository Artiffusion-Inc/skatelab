package ru.skatelab.shared.models

sealed interface AppError {
    val messageKey: String

    data class Network(
        override val messageKey: String = "error_network",
    ) : AppError

    data class Auth(
        override val messageKey: String = "error_auth",
    ) : AppError

    data class NotFound(
        override val messageKey: String = "error_not_found",
    ) : AppError

    data class Server(
        override val messageKey: String = "error_server",
    ) : AppError

    /**
     * HTTP 409 Conflict — backend carries an actionable detail (e.g. "Email already registered")
     * in the response body `error`/`message` field. `detail` preserves that text so the UI can
     * surface it instead of the generic "unknown error".
     *
     * `messageKey` defaults to the dedicated `error_conflict` localization; when `detail` is
     * present the UI may surface it directly for actionable guidance (e.g. "Email already
     * registered" → "try another email or log in").
     */
    data class Conflict(
        override val messageKey: String = "error_conflict",
        val detail: String? = null,
    ) : AppError

    data class Timeout(
        override val messageKey: String = "error_timeout",
    ) : AppError

    data class Unknown(
        override val messageKey: String = "error_unknown",
        val detail: String? = null,
    ) : AppError
}
