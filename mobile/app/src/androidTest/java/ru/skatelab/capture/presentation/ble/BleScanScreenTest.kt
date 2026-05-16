package ru.skatelab.capture.presentation.ble

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import org.junit.Rule
import org.junit.Test

class BleScanScreenTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun composeTestRule_worksOnDevice() {
        composeRule.setContent {
            MaterialTheme {
                Text("BLE Sensor Scan")
            }
        }

        composeRule.onNodeWithText("BLE Sensor Scan").assertIsDisplayed()
    }
}
