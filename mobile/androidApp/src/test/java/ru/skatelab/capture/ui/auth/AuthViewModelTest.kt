package ru.skatelab.capture.ui.auth

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.shared.api.UsersApi
import ru.skatelab.shared.auth.AuthRepository
import ru.skatelab.shared.models.UserResponse
import ru.skatelab.shared.state.AuthUiState
import ru.skatelab.shared.state.AuthViewModel

@OptIn(ExperimentalCoroutinesApi::class)
class AuthViewModelTest {
    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)

    private lateinit var authRepo: AuthRepository
    private lateinit var usersApi: UsersApi
    private lateinit var viewModel: AuthViewModel

    @Before
    fun setUp() {
        authRepo = mockk(relaxed = true)
        usersApi = mockk(relaxed = true)
        viewModel = AuthViewModel(authRepo, usersApi)
    }

    @Test
    fun checkLogin_loggedIn_setsLoggedInState() =
        testScope.runTest {
            coEvery { authRepo.isLoggedIn() } returns true
            coEvery { usersApi.getMe() } returns
                UserResponse(
                    id = "u1", email = "test@test.com", displayName = "Alice",
                    avatarUrl = null, bio = null, heightCm = null, weightKg = null,
                    language = "ru", timezone = "Europe/Moscow", theme = "dark",
                    onboardingRole = "athlete", angularUnit = "deg_per_sec",
                )

            viewModel.checkLogin()
            advanceUntilIdle()

            val state = viewModel.uiState.value
            assertTrue(state is AuthUiState.LoggedIn)
            assertEquals("u1", (state as AuthUiState.LoggedIn).userId)
            assertEquals("Alice", state.displayName)
        }

    @Test
    fun checkLogin_notLoggedIn_setsLoggedOutState() =
        testScope.runTest {
            coEvery { authRepo.isLoggedIn() } returns false

            viewModel.checkLogin()
            advanceUntilIdle()

            assertTrue(viewModel.uiState.value is AuthUiState.LoggedOut)
        }

    @Test
    fun login_success_setsLoggedInState() =
        testScope.runTest {
            coEvery { authRepo.login("test@test.com", "pass") } returns Result.success(Unit)
            coEvery { usersApi.getMe() } returns
                UserResponse(
                    id = "u1", email = "test@test.com", displayName = "Alice",
                    avatarUrl = null, bio = null, heightCm = null, weightKg = null,
                    language = "ru", timezone = "Europe/Moscow", theme = "dark",
                    onboardingRole = "athlete", angularUnit = "deg_per_sec",
                )

            viewModel.login("test@test.com", "pass")
            advanceUntilIdle()

            val state = viewModel.uiState.value
            assertTrue(state is AuthUiState.LoggedIn)
            coVerify { authRepo.login("test@test.com", "pass") }
        }

    @Test
    fun login_failure_setsErrorState() =
        testScope.runTest {
            coEvery { authRepo.login("bad@test.com", "wrong") } returns
                Result.failure(IllegalStateException("Invalid credentials"))

            viewModel.login("bad@test.com", "wrong")
            advanceUntilIdle()

            val state = viewModel.uiState.value
            assertTrue(state is AuthUiState.Error)
            assertTrue((state as AuthUiState.Error).error.messageKey.isNotEmpty())
        }

    @Test
    fun register_success_setsLoggedInState() =
        testScope.runTest {
            coEvery { authRepo.register("new@test.com", "pass", "Bob") } returns Result.success(Unit)
            coEvery { usersApi.getMe() } returns
                UserResponse(
                    id = "u2", email = "new@test.com", displayName = "Bob",
                    avatarUrl = null, bio = null, heightCm = null, weightKg = null,
                    language = "ru", timezone = "Europe/Moscow", theme = "dark",
                    onboardingRole = "athlete", angularUnit = "deg_per_sec",
                )

            viewModel.register("new@test.com", "pass", "Bob")
            advanceUntilIdle()

            assertTrue(viewModel.uiState.value is AuthUiState.LoggedIn)
            coVerify { authRepo.register("new@test.com", "pass", "Bob") }
        }

    @Test
    fun logout_setsLoggedOutState() =
        testScope.runTest {
            coEvery { authRepo.logout() } returns Unit

            viewModel.logout()
            advanceUntilIdle()

            assertTrue(viewModel.uiState.value is AuthUiState.LoggedOut)
            coVerify { authRepo.logout() }
        }
}
