package ru.skatelab.capture.ui.profile

import io.ktor.client.plugins.ClientRequestException
import io.ktor.client.statement.HttpResponse
import io.ktor.http.HttpStatusCode
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Before
import org.junit.Test
import ru.skatelab.shared.api.SkateLabClient
import ru.skatelab.shared.api.UsersApi
import ru.skatelab.shared.auth.AuthRepository
import ru.skatelab.shared.state.AuthViewModel as SharedAuthViewModel

/**
 * Repro for NEW bug — ProfileViewModel surfaces raw HTTP exception text (not AppError) on auth failure.
 *
 * Root cause: `ProfileViewModel` stores failures as `error: String? = e.message ?: "Failed..."`
 * (ProfileViewModel.kt:18, :58, :87, :111) — using the RAW `Throwable.message`, NOT
 * `e.toAppError()` (ExceptionMapping.kt). So a real 401 from `usersApi.getMe()` arrives as a
 * `ClientRequestException` whose `message` is the raw Ktor HTTP text
 * (e.g. "Client request(GET https://api.skatelab.ru/v1/users/me) invalid: 401 Unauthorized"),
 * which is:
 *   - technical / English / not localized (no `messageKey`),
 *   - indistinguishable from a server error or a network error (no `AppError` type — `error` is a
 *     bare `String?`, not `AppError`), so the UI cannot route the user to a re-login flow.
 *
 * Contrast: `SessionsViewModel` and the rest of the shared layer use
 * `catch (e) { Error(e.toAppError()) }` → 401 → `AppError.Auth()` (messageKey `error_auth`),
 * which the UI maps to localized text + a re-login affordance. `ProfileViewModel` diverges: it
 * bypasses `toAppError()` entirely, so an expired-token user editing their profile sees raw Ktor
 * HTTP English text in the error label — an inconsistent, un-professional recovery story, and
 * silently the wrong UX for an auth failure (no re-login routing).
 *
 * Why the existing `ProfileViewModelTest.loadProfile_failure_setsError` misses this: it throws a
 * generic `RuntimeException("Network error")` (line 85) and asserts `error.contains("Network
 * error")` (line 92) — a test-double artifact (#319-style): the test verifies string-pass-through,
 * NOT the real mapping. It never exercises a `ResponseException` with an HTTP status, so the
 * auth/server/not-found indistinguishability never surfaces in CI.
 *
 * This repro throws a REAL `ClientRequestException` carrying `HttpResponse(401)` — what
 * `UsersApi.getMe().expectSuccess()` actually raises in prod — and pins the contract: a 401 must
 * NOT leak raw HTTP status text into user-facing `error`; it must surface an auth-aware signal
 * (ideally the state should carry `AppError.Auth`, but at minimum `error` must not contain the
 * raw "401" HTTP code / "Unauthorized" technical string).
 *
 * RED now: `error` contains the raw `ClientRequestException.message` (includes "401" and
 * "Unauthorized"). After the fix — routing through `e.toAppError()` and exposing `AppError`
 * (or at least a localized, auth-distinct string) — this goes GREEN.
 *
 * Proposed fix (separate PR): change `ProfileUiState.error` from `String?` to `AppError?` (or add
 * an `appError: AppError?` field), and set it via `e.toAppError()` in `loadProfile`/`updateProfile`/
 * `updateSettings` `onFailure` — matching SessionsViewModel. UI renders `error.messageKey` via
 * `stringResource()` and routes `AppError.Auth` to re-login.
 */
@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class ProfileAuthFailureRawMessageReproTest {
    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)

    private lateinit var client: SkateLabClient
    private lateinit var usersApi: UsersApi
    private lateinit var authRepository: AuthRepository
    private lateinit var sharedAuthViewModel: SharedAuthViewModel
    private lateinit var viewModel: ProfileViewModel

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        usersApi = mockk(relaxed = true)
        authRepository = mockk(relaxed = true)
        sharedAuthViewModel = SharedAuthViewModel(authRepository, usersApi)
        client = mockk<SkateLabClient>()
        every { client.users } returns usersApi
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun loadProfile_401_mustNotLeakRawHttpStatusText_repro() =
        testScope.runTest {
            // Build a REAL ClientRequestException carrying a 401 HttpResponse — exactly what
            // UsersApi.getMe().expectSuccess() throws in prod when the token is expired/invalid.
            val mockResponse = mockk<HttpResponse>(relaxed = true)
            every { mockResponse.status } returns HttpStatusCode.Unauthorized
            val authException =
                ClientRequestException(mockResponse, "Unauthorized")

            coEvery { usersApi.getMe() } throws authException

            viewModel = ProfileViewModel(client, sharedAuthViewModel)
            advanceUntilIdle()

            val state = viewModel.uiState.value
            assertFalse("isLoading should be false after failure", state.isLoading)
            assertNotNull("error must be set on failure", state.error)
            val errorText = state.error!!

            // CONTRACT: an auth failure must surface a localized / auth-distinct signal, NOT the raw
            // HTTP status. The raw ClientRequestException.message embeds the literal "401" and
            // "Unauthorized" technical tokens — leaking them to the user is the bug.
            assertFalse(
                "BUG: ProfileViewModel leaks raw HTTP status into user-facing error. " +
                    "A 401 must be mapped to AppError.Auth (localized, auth-distinct), not the raw " +
                    "Ktor exception text. Got: \"$errorText\"",
                errorText.contains("401", ignoreCase = true) ||
                    errorText.contains("Unauthorized", ignoreCase = true),
            )

            // Additionally: the state should carry an AppError.Auth so the UI can route to re-login.
            // (Currently ProfileUiState.error is String? and holds no AppError — this assertion
            // documents the design gap; the assertFalse above is the primary RED signal.)
            // No AppError accessor exists today, so we assert the negative on raw HTTP text only.
        }
}
