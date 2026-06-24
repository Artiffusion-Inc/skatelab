package ru.skatelab.shared.utils

import io.ktor.client.plugins.ResponseException
import io.ktor.client.statement.HttpResponse
import io.ktor.http.isSuccess

/**
 * Throws [ResponseException] if the response status is not a success (2xx),
 * otherwise returns the receiver. Call before `.body<T>()` so a 4xx error-body
 * (e.g. `{"detail":"..."}`) surfaces as a [ResponseException] — mapped by
 * [Throwable.toAppError] to [ru.skatelab.shared.models.AppError.Auth] /
 * [ru.skatelab.shared.models.AppError.NotFound] /
 * [ru.skatelab.shared.models.AppError.Server] by HTTP status — instead of a
 * [io.ktor.serialization.JsonConvertException] (deserializing the error body
 * into the success model) that falls through to
 * [ru.skatelab.shared.models.AppError.Unknown].
 */
fun HttpResponse.expectSuccess(): HttpResponse {
    if (!status.isSuccess()) {
        throw ResponseException(this, status.description)
    }
    return this
}