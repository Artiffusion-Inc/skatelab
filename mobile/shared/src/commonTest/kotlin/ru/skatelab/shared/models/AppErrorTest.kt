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
        assertEquals("boom", err.detail)
    }

    @Test
    fun httpStatusCodeToAppError_maps401ToAuth() {
        assertIs<AppError.Auth>(HttpStatusCode.Unauthorized.toAppError())
    }

    @Test
    fun httpStatusCodeToAppError_maps400And422ToAuth() {
        assertIs<AppError.Auth>(HttpStatusCode.BadRequest.toAppError())
        assertIs<AppError.Auth>(HttpStatusCode.UnprocessableEntity.toAppError())
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
