package ru.skatelab.capture.presentation.ble

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.ScanDevice

class BleScanScreenTest {

    @get:Rule
    val composeRule = createComposeRule()

    private lateinit var viewModel: BleScanViewModel

    private val scanResultsFlow = MutableStateFlow<List<ScanDevice>>(emptyList())
    private val connectionStateFlow = MutableStateFlow<Map<SensorId, BleRepository.ConnectionState>>(emptyMap())

    @Before
    fun setUp() {
        val bleRepository = mockk<BleRepository>(relaxed = true)
        val connectUseCase = mockk<ru.skatelab.capture.domain.usecase.ConnectSensorUseCase>(relaxed = true)

        every { bleRepository.scanResults } returns scanResultsFlow
        every { bleRepository.connectionState } returns connectionStateFlow

        viewModel = BleScanViewModel(bleRepository, connectUseCase)
    }

    @Test
    fun scanScreen_displaysTitle() {
        composeRule.setContent {
            BleScanScreen(viewModel = viewModel, onProceed = {})
        }

        composeRule.onNodeWithText("BLE Sensor Scan").assertIsDisplayed()
    }

    @Test
    fun scanScreen_displaysScanButton() {
        composeRule.setContent {
            BleScanScreen(viewModel = viewModel, onProceed = {})
        }

        composeRule.onNodeWithText("Scan").assertIsDisplayed()
    }

    @Test
    fun scanScreen_tapScan_startsScanning() {
        composeRule.setContent {
            BleScanScreen(viewModel = viewModel, onProceed = {})
        }

        composeRule.onNodeWithText("Scan").performClick()

        assert(viewModel.isScanning)
    }

    @Test
    fun scanScreen_displaysDeviceWhenFound() {
        scanResultsFlow.value = listOf(ScanDevice("WT901", "AA:BB:CC", -45))

        composeRule.setContent {
            BleScanScreen(viewModel = viewModel, onProceed = {})
        }

        composeRule.onNodeWithText("WT901").assertIsDisplayed()
    }
}
