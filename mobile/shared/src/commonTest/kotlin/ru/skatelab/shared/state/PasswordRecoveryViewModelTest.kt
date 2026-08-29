package ru.skatelab.shared.state

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlinx.coroutines.test.runTest
import ru.skatelab.shared.models.AppError

class PasswordRecoveryViewModelTest {
    private class FakeRecoveryApi(
        private val failure: Exception? = null,
    ) : AuthRecoveryApi {
        var requestedEmail: String? = null

        override suspend fun forgotPassword(email: String) {
            requestedEmail = email
            failure?.let { throw it }
        }
    }

    @Test
    fun requestReset_trimsEmailAndEmitsSent() = runTest {
        val api = FakeRecoveryApi()
        val viewModel = PasswordRecoveryViewModel(api)

        viewModel.requestReset("  skater@example.com ")

        assertEquals("skater@example.com", api.requestedEmail)
        assertIs<PasswordRecoveryUiState.Sent>(viewModel.uiState.value)
    }

    @Test
    fun requestReset_failureEmitsError() = runTest {
        val viewModel = PasswordRecoveryViewModel(FakeRecoveryApi(RuntimeException("offline")))

        viewModel.requestReset("skater@example.com")

        assertIs<PasswordRecoveryUiState.Error>(viewModel.uiState.value)
        assertIs<AppError.Unknown>((viewModel.uiState.value as PasswordRecoveryUiState.Error).error)
    }
}
