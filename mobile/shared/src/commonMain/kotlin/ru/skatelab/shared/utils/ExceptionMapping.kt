package ru.skatelab.shared.utils

import io.ktor.client.network.sockets.SocketTimeoutException
import io.ktor.client.plugins.HttpRequestTimeoutException
import io.ktor.client.plugins.ResponseException
import io.ktor.http.HttpStatusCode
import kotlinx.io.IOException
import ru.skatelab.shared.models.AppError

fun Throwable.toAppError(): AppError =
    when (this) {
        is SocketTimeoutException, is HttpRequestTimeoutException -> AppError.Timeout()
        is ResponseException -> this.response.status.toAppError(detail = this.message)
        is IOException -> AppError.Network()
        else -> {
            val throwable = this
            val detail = buildString {
                append(throwable::class.simpleName ?: "Unknown")
                if (!throwable.message.isNullOrEmpty()) append(": ${throwable.message}")
                throwable.cause?.let {
                    append(" | caused by: ${it::class.simpleName ?: "?"}: ${it.message ?: ""}")
                }
            }
            AppError.Unknown(detail = detail)
        }
    }

/**
 * Map an HTTP status to an `AppError`. `detail` is the backend response-body detail carried by the
 * `ResponseException.message` (see `AuthApi` — it reads the body and throws with that detail
 * instead of the HTTP reason-phrase). The 400/422 Validation and 409 Conflict branches surface
 * `detail` (the actionable backend text — "password: field too short", "Email already
 * registered"); 401/403/404/5xx ignore it for localized-only behavior.
 */
fun HttpStatusCode.toAppError(detail: String? = null): AppError =
    when (value) {
        400, 422 -> AppError.Validation(detail = detail)
        401, 403 -> AppError.Auth()
        404 -> AppError.NotFound()
        409 -> AppError.Conflict(detail = detail)
        in 500..599 -> AppError.Server()
        else -> AppError.Unknown()
    }
