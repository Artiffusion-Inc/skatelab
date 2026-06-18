package ru.skatelab.capture.ui.profile

import io.mockk.coEvery
import io.mockk.coVerify
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
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.shared.api.SkateLabClient
import ru.skatelab.shared.api.UsersApi
import ru.skatelab.shared.auth.AuthRepository
import ru.skatelab.shared.models.UserResponse
import ru.skatelab.shared.state.AuthViewModel as SharedAuthViewModel

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class ProfileViewModelTest {
    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)

    private lateinit var client: SkateLabClient
    private lateinit var usersApi: UsersApi
    private lateinit var authRepository: AuthRepository
    private lateinit var sharedAuthViewModel: SharedAuthViewModel
    private lateinit var viewModel: ProfileViewModel

    private val stubUser =
        UserResponse(
            id = "u1",
            email = "skater@example.com",
            displayName = "Alice",
            bio = "Figure skater",
            heightCm = 165.0,
            weightKg = 52.0,
            language = "ru",
            timezone = "Europe/Moscow",
            theme = "dark",
            onboardingRole = "athlete",
            angularUnit = "deg_per_sec",
        )

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        usersApi = mockk(relaxed = true)
        authRepository = mockk(relaxed = true)
        sharedAuthViewModel = SharedAuthViewModel(authRepository, usersApi)
        client = mockk<SkateLabClient>()
        every { client.users } returns usersApi
        coEvery { usersApi.getMe() } returns stubUser
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun init_loadsProfile() =
        testScope.runTest {
            viewModel = ProfileViewModel(client, sharedAuthViewModel)
            advanceUntilIdle()

            coVerify { usersApi.getMe() }
            assertFalse(viewModel.uiState.value.isLoading)
            assertEquals("u1", viewModel.uiState.value.profile?.id)
            assertNull(viewModel.uiState.value.error)
        }

    @Test
    fun loadProfile_failure_setsError() =
        testScope.runTest {
            coEvery { usersApi.getMe() } throws RuntimeException("Network error")

            viewModel = ProfileViewModel(client, sharedAuthViewModel)
            advanceUntilIdle()

            assertFalse(viewModel.uiState.value.isLoading)
            assertNotNull(viewModel.uiState.value.error)
            assertTrue(viewModel.uiState.value.error!!.contains("Network error"))
        }

    @Test
    fun updateProfile_success_updatesState() =
        testScope.runTest {
            val updated = stubUser.copy(displayName = "Alice Updated")
            coEvery { usersApi.updateProfile(displayName = "Alice Updated") } returns updated

            viewModel = ProfileViewModel(client, sharedAuthViewModel)
            advanceUntilIdle()

            viewModel.updateProfile(displayName = "Alice Updated")
            advanceUntilIdle()

            coVerify { usersApi.updateProfile(displayName = "Alice Updated") }
            assertEquals("Alice Updated", viewModel.uiState.value.profile?.displayName)
            assertTrue(viewModel.uiState.value.saveSuccess)
        }

    @Test
    fun updateProfile_failure_setsError() =
        testScope.runTest {
            coEvery { usersApi.updateProfile(any(), any(), any(), any()) } throws
                RuntimeException("Save failed")

            viewModel = ProfileViewModel(client, sharedAuthViewModel)
            advanceUntilIdle()

            viewModel.updateProfile(displayName = "New")
            advanceUntilIdle()

            assertFalse(viewModel.uiState.value.isSaving)
            assertTrue(viewModel.uiState.value.error!!.contains("Save failed"))
        }

    @Test
    fun updateSettings_success() =
        testScope.runTest {
            val updated = stubUser.copy(angularUnit = "rad_per_sec")
            coEvery { usersApi.updateSettings(angularUnit = "rad_per_sec") } returns updated

            viewModel = ProfileViewModel(client, sharedAuthViewModel)
            advanceUntilIdle()

            viewModel.updateSettings("rad_per_sec")
            advanceUntilIdle()

            coVerify { usersApi.updateSettings(angularUnit = "rad_per_sec") }
            assertEquals("rad_per_sec", viewModel.uiState.value.profile?.angularUnit)
        }

    @Test
    fun logout_callsSharedAuthViewModel() =
        testScope.runTest {
            viewModel = ProfileViewModel(client, sharedAuthViewModel)
            advanceUntilIdle()

            viewModel.logout()
            advanceUntilIdle()

            coVerify { authRepository.logout() }
            assertTrue(viewModel.isLoggedOut.value)
        }

    @Test
    fun clearError_resetsError() =
        testScope.runTest {
            coEvery { usersApi.getMe() } throws RuntimeException("err")

            viewModel = ProfileViewModel(client, sharedAuthViewModel)
            advanceUntilIdle()

            assertNotNull(viewModel.uiState.value.error)
            viewModel.clearError()
            assertNull(viewModel.uiState.value.error)
        }
}
