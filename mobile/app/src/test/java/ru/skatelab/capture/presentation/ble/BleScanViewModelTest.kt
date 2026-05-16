package ru.skatelab.capture.presentation.ble

import androidx.lifecycle.viewModelScope
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.ScanDevice
import ru.skatelab.capture.domain.service.Logger
import ru.skatelab.capture.domain.usecase.AccCalibrateSensorUseCase
import ru.skatelab.capture.domain.usecase.ConnectSensorUseCase
import ru.skatelab.capture.domain.usecase.FactoryResetSensorUseCase

class BleScanViewModelTest {
    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)

    private lateinit var bleRepository: BleRepository
    private lateinit var connectSensorUseCase: ConnectSensorUseCase
    private lateinit var factoryResetSensorUseCase: FactoryResetSensorUseCase
    private lateinit var accCalibrateSensorUseCase: AccCalibrateSensorUseCase
    private lateinit var appLogger: Logger
    private lateinit var viewModel: BleScanViewModel

    private val scanResultsFlow = MutableStateFlow<List<ScanDevice>>(emptyList())
    private val connectionStateFlow = MutableStateFlow<Map<SensorId, BleRepository.ConnectionState>>(emptyMap())

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        bleRepository = mockk(relaxed = true)
        connectSensorUseCase = mockk(relaxed = true)
        factoryResetSensorUseCase = mockk(relaxed = true)
        accCalibrateSensorUseCase = mockk(relaxed = true)
        appLogger = mockk(relaxed = true)

        every { bleRepository.scanResults } returns scanResultsFlow
        every { bleRepository.connectionState } returns connectionStateFlow

        viewModel =
            BleScanViewModel(
                bleRepository,
                connectSensorUseCase,
                factoryResetSensorUseCase,
                accCalibrateSensorUseCase,
                appLogger,
            )
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun startScan_setsScanning() {
        assertFalse(viewModel.isScanning)
        viewModel.startScan()
        assertTrue(viewModel.isScanning)
        verify { bleRepository.startScan() }
    }

    @Test
    fun startScan_idempotent() {
        viewModel.startScan()
        viewModel.startScan()
        verify(exactly = 1) { bleRepository.startScan() }
    }

    @Test
    fun stopScan_clearsScanning() {
        viewModel.startScan()
        assertTrue(viewModel.isScanning)

        viewModel.stopScan()
        assertFalse(viewModel.isScanning)

        verify { bleRepository.stopScan() }
    }

    @Test
    fun connectSensor_success_noException() =
        testScope.runTest {
            coEvery { connectSensorUseCase.invoke(SensorId.LEFT, "AA:BB:CC:DD:EE:FF") } returns Result.success(Unit)

            viewModel.connectSensor(SensorId.LEFT, "AA:BB:CC:DD:EE:FF")
            advanceUntilIdle()
        }

    @Test
    fun connectSensor_failure_noException() =
        testScope.runTest {
            coEvery { connectSensorUseCase.invoke(SensorId.RIGHT, "11:22:33:44:55:66") } returns
                Result.failure(IllegalStateException("Connection failed"))

            viewModel.connectSensor(SensorId.RIGHT, "11:22:33:44:55:66")
            advanceUntilIdle()
        }

    @Test
    fun `getAddressForSensor delegates to repository`() =
        testScope.runTest {
            every { bleRepository.getAddressForSensor(SensorId.LEFT) } returns "AA:BB:CC:DD:EE:FF"
            assertEquals("AA:BB:CC:DD:EE:FF", viewModel.getAddressForSensor(SensorId.LEFT))
        }

    @Test
    fun `scanResults merges connected devices`() =
        testScope.runTest {
            val connectedDevice = ScanDevice("WT901", "AA:BB:CC:DD:EE:FF", 0)
            every { bleRepository.getConnectedDevices() } returns listOf(connectedDevice)
            scanResultsFlow.value = emptyList()

            val collectJob = viewModel.viewModelScope.launch { viewModel.scanResults.collect {} }

            advanceUntilIdle()

            val result = viewModel.scanResults.value
            assertTrue("Connected device should appear in scan results", result.any { it.address == "AA:BB:CC:DD:EE:FF" })

            collectJob.cancel()
        }
}
