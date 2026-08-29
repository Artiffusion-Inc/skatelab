package ru.skatelab.shared.state

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.AuthApi
import ru.skatelab.shared.models.AppError

class NewPasswordViewModelTest {
    private fun api(status: HttpStatusCode = HttpStatusCode.OK): AuthApi =
        AuthApi(
            HttpClient(
                MockEngine {
                    respond(
                        content = "{}",
                        status = status,
                        headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                    )
                },
            ) {
                install(ContentNegotiation) { json(Json { ignoreUnknownKeys = true }) }
            },
        )

    @Test
    fun resetPassword_trimsToken_andEmitsSuccess() = runTest {
        val viewModel = NewPasswordViewModel(api())

        viewModel.resetPassword("  reset-token ", "new-password")

        assertIs<NewPasswordUiState.Success>(viewModel.uiState.value)
    }

    @Test
    fun resetPassword_failureEmitsError() = runTest {
        val viewModel = NewPasswordViewModel(api(HttpStatusCode.BadRequest))

        viewModel.resetPassword("expired-token", "new-password")

        val state = assertIs<NewPasswordUiState.Error>(viewModel.uiState.value)
        assertEquals("error_validation", state.error.messageKey)
        assertIs<AppError.Validation>(state.error)
    }
}
