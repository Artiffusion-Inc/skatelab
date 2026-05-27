package ru.skatelab.shared.models

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class AppErrorTest {

    @Test
    fun appErrorSubtypesHaveCorrectMessageKeys() {
        assertEquals("error_network", AppError.Network().messageKey)
        assertEquals("error_auth", AppError.Auth().messageKey)
        assertEquals("error_not_found", AppError.NotFound().messageKey)
        assertEquals("error_server", AppError.Server().messageKey)
        assertEquals("error_timeout", AppError.Timeout().messageKey)
        assertEquals("error_unknown", AppError.Unknown().messageKey)
    }

    @Test
    fun appErrorSubtypesAreDataClasses() {
        val err = AppError.Network()
        assertIs<AppError.Network>(err)
        assertEquals(AppError.Network(), AppError.Network())
        assertEquals(AppError.Auth(), AppError.Auth())
    }
}
