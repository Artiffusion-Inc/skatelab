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
        is ResponseException -> this.response.status.toAppError()
        is IOException -> AppError.Network()
        else -> {
            val detail = buildString {
                append(this::class.simpleName ?: "Unknown")
                if (!message.isNullOrEmpty()) append(": $message")
                cause?.let { append(" | caused by: ${it::class.simpleName ?: "?"}: ${it.message ?: ""}") }
            }
            AppError.Unknown(detail = detail)
        }
    }

fun HttpStatusCode.toAppError(): AppError =
    when (value) {
        400, 422 -> AppError.Auth()
        401, 403 -> AppError.Auth()
        404 -> AppError.NotFound()
        in 500..599 -> AppError.Server()
        else -> AppError.Unknown()
    }
