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

class VerifyEmailViewModelTest {
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
    fun verifyEmail_trimsToken_andEmitsVerified() = runTest {
        val viewModel = VerifyEmailViewModel(api())

        viewModel.verifyEmail("  verify-token ")

        assertIs<VerifyEmailUiState.Verified>(viewModel.uiState.value)
    }

    @Test
    fun resendVerification_trimsEmail_andEmitsSent() = runTest {
        val viewModel = VerifyEmailViewModel(api())

        viewModel.resendVerification("  skater@example.com ")

        assertIs<VerifyEmailUiState.Sent>(viewModel.uiState.value)
    }

    @Test
    fun verifyEmail_failureEmitsError() = runTest {
        val viewModel = VerifyEmailViewModel(api(HttpStatusCode.BadRequest))

        viewModel.verifyEmail("expired-token")

        val state = assertIs<VerifyEmailUiState.Error>(viewModel.uiState.value)
        assertEquals("error_validation", state.error.messageKey)
    }
}
