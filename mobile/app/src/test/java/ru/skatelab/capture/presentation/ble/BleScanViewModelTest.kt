package ru.skatelab.capture.presentation.ble

import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.ScanDevice
import ru.skatelab.capture.domain.usecase.ConnectSensorUseCase

class BleScanViewModelTest {

    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)

    private lateinit var bleRepository: BleRepository
    private lateinit var connectSensorUseCase: ConnectSensorUseCase
    private lateinit var viewModel: BleScanViewModel

    private val scanResultsFlow = MutableStateFlow<List<ScanDevice>>(emptyList())
    private val connectionStateFlow = MutableStateFlow<Map<SensorId, BleRepository.ConnectionState>>(emptyMap())

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        connectSensorUseCase = mockk(relaxed = true)

        every { bleRepository.scanResults } returns scanResultsFlow
        every { bleRepository.connectionState } returns connectionStateFlow

        viewModel = BleScanViewModel(bleRepository, connectSensorUseCase)
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
    fun connectSensor_success_noException() = testScope.runTest {
        coEvery { connectSensorUseCase.invoke(SensorId.LEFT, "AA:BB:CC:DD:EE:FF") } returns Result.success(Unit)

        viewModel.connectSensor(SensorId.LEFT, "AA:BB:CC:DD:EE:FF")
        advanceUntilIdle()
    }

    @Test
    fun connectSensor_failure_noException() = testScope.runTest {
        coEvery { connectSensorUseCase.invoke(SensorId.RIGHT, "11:22:33:44:55:66") } returns
            Result.failure(IllegalStateException("Connection failed"))

        viewModel.connectSensor(SensorId.RIGHT, "11:22:33:44:55:66")
        advanceUntilIdle()
    }
}
