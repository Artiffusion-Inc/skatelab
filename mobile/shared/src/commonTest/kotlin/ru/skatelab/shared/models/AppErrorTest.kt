package ru.skatelab.shared.models

import io.ktor.client.network.sockets.SocketTimeoutException
import io.ktor.client.plugins.HttpRequestTimeoutException
import io.ktor.http.HttpStatusCode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlinx.io.IOException
import ru.skatelab.shared.utils.toAppError

class AppErrorTest {
    @Test
    fun appErrorSubtypesHaveCorrectMessageKeys() {
        assertEquals("error_network", AppError.Network().messageKey)
        assertEquals("error_auth", AppError.Auth().messageKey)
        assertEquals("error_validation", AppError.Validation().messageKey)
        assertEquals("error_validation", AppError.Validation(detail = "d").messageKey)
        assertEquals("d", AppError.Validation(detail = "d").detail)
        assertEquals("error_not_found", AppError.NotFound().messageKey)
        assertEquals("error_server", AppError.Server().messageKey)
        assertEquals("error_timeout", AppError.Timeout().messageKey)
        assertEquals("error_unknown", AppError.Unknown().messageKey)
        assertEquals("error_unknown", AppError.Unknown(detail = "detail").messageKey)
        assertEquals("detail", AppError.Unknown(detail = "detail").detail)
    }

    @Test
    fun appErrorSubtypesAreDataClasses() {
        val err = AppError.Network()
        assertIs<AppError.Network>(err)
        assertEquals(AppError.Network(), AppError.Network())
        assertEquals(AppError.Auth(), AppError.Auth())
    }

    @Test
    fun toAppError_mapsTimeoutExceptions() {
        assertIs<AppError.Timeout>(SocketTimeoutException("timeout").toAppError())
        assertIs<AppError.Timeout>(HttpRequestTimeoutException("https://example.com", timeoutMillis = 30_000).toAppError())
    }

    @Test
    fun toAppError_mapsIOExceptionToNetwork() {
        assertIs<AppError.Network>(IOException().toAppError())
    }

    @Test
    fun toAppError_mapsUnknownToUnknownWithDetail() {
        val err = RuntimeException("boom").toAppError()
        assertIs<AppError.Unknown>(err)
        assertEquals("RuntimeException: boom", err.detail)
    }

    @Test
    fun toAppError_unknownDetailIncludesCause() {
        val err = RuntimeException("boom", IllegalStateException("root")).toAppError()
        assertIs<AppError.Unknown>(err)
        assertEquals("RuntimeException: boom | caused by: IllegalStateException: root", err.detail)
    }

    @Test
    fun httpStatusCodeToAppError_maps401ToAuth() {
        assertIs<AppError.Auth>(HttpStatusCode.Unauthorized.toAppError())
    }

    @Test
    fun httpStatusCodeToAppError_maps400And422ToValidation() {
        // 400/422 are input-validation failures, NOT auth failures (#444). They carry the
        // backend Pydantic detail so the UI surfaces actionable guidance, not "log in again".
        assertIs<AppError.Validation>(HttpStatusCode.BadRequest.toAppError())
        assertIs<AppError.Validation>(HttpStatusCode.UnprocessableEntity.toAppError())
        val validation = HttpStatusCode.BadRequest.toAppError("password: field too short")
        assertIs<AppError.Validation>(validation)
        assertEquals("password: field too short", validation.detail)
        assertIs<AppError.Auth>(HttpStatusCode.Forbidden.toAppError())
    }

    @Test
    fun httpStatusCodeToAppError_maps404ToNotFound() {
        assertIs<AppError.NotFound>(HttpStatusCode.NotFound.toAppError())
    }

    @Test
    fun httpStatusCodeToAppError_maps5xxToServer() {
        assertIs<AppError.Server>(HttpStatusCode.InternalServerError.toAppError())
        assertIs<AppError.Server>(HttpStatusCode(503, "Service Unavailable").toAppError())
    }
}
