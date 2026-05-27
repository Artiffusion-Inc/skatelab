package ru.skatelab.capture.a11y

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.tryPerformAccessibilityChecks
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import ru.skatelab.capture.presentation.theme.AppTheme
import ru.skatelab.capture.ui.auth.LoginScreen
import ru.skatelab.capture.ui.auth.RegisterScreen
import ru.skatelab.shared.state.AuthUiState

@RunWith(AndroidJUnit4::class)
class AccessibilityTest {
    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun loginScreenHasNoAccessibilityIssues() {
        composeTestRule.setContent {
            AppTheme {
                LoginScreen(
                    uiState = AuthUiState.LoggedOut,
                    onLogin = { _, _ -> },
                    onNavigateToRegister = {},
                    onNavigateToCamera = {},
                )
            }
        }
        composeTestRule.onRoot().tryPerformAccessibilityChecks()
    }

    @Test
    fun registerScreenHasNoAccessibilityIssues() {
        composeTestRule.setContent {
            AppTheme {
                RegisterScreen(
                    uiState = AuthUiState.LoggedOut,
                    onRegister = { _, _, _ -> },
                    onNavigateToLogin = {},
                    onNavigateToCamera = {},
                )
            }
        }
        composeTestRule.onRoot().tryPerformAccessibilityChecks()
    }
}
