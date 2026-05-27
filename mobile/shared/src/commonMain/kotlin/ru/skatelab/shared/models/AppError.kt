package ru.skatelab.shared.models

sealed interface AppError {
    val messageKey: String

    data class Network(override val messageKey: String = "error_network") : AppError
    data class Auth(override val messageKey: String = "error_auth") : AppError
    data class NotFound(override val messageKey: String = "error_not_found") : AppError
    data class Server(override val messageKey: String = "error_server") : AppError
    data class Timeout(override val messageKey: String = "error_timeout") : AppError
    data class Unknown(override val messageKey: String = "error_unknown") : AppError
}
