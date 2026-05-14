package ru.skatelab.capture.presentation.ble

import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
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
import ru.skatelab.capture.domain.model.SensorInfo
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.ScanDevice
import ru.skatelab.capture.domain.service.Logger
import ru.skatelab.capture.domain.usecase.AccCalibrateSensorUseCase
import ru.skatelab.capture.domain.usecase.ConnectSensorUseCase
import ru.skatelab.capture.domain.usecase.FactoryResetSensorUseCase
import ru.skatelab.capture.domain.usecase.ReadSensorInfoUseCase

class BleScanViewModelTest {
    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)

    private lateinit var bleRepository: BleRepository
    private lateinit var connectSensorUseCase: ConnectSensorUseCase
    private lateinit var factoryResetSensorUseCase: FactoryResetSensorUseCase
    private lateinit var accCalibrateSensorUseCase: AccCalibrateSensorUseCase
    private lateinit var appLogger: Logger
    private lateinit var readSensorInfoUseCase: ReadSensorInfoUseCase
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
        readSensorInfoUseCase = mockk(relaxed = true)

        every { bleRepository.scanResults } returns scanResultsFlow
        every { bleRepository.connectionState } returns connectionStateFlow

        viewModel =
            BleScanViewModel(
                bleRepository,
                connectSensorUseCase,
                factoryResetSensorUseCase,
                accCalibrateSensorUseCase,
                appLogger,
                readSensorInfoUseCase,
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
    fun `auto-refresh sensorInfo on connect`() =
        testScope.runTest {
            val info = SensorInfo(deviceId = "A3F2", firmwareVersion = "1.0", batteryPercent = 85, batteryMv = 3850)
            coEvery { readSensorInfoUseCase(SensorId.LEFT) } returns Result.success(info)

            connectionStateFlow.value = mapOf(SensorId.LEFT to BleRepository.ConnectionState.CONNECTED)
            advanceUntilIdle()

            assertEquals(info, viewModel.sensorInfo.value[SensorId.LEFT])
        }
}
