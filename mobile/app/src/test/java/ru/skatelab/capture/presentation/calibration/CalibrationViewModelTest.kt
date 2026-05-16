package ru.skatelab.capture.presentation.calibration

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.usecase.CalibrateSensorUseCase
import ru.skatelab.capture.domain.usecase.StartStreamingUseCase
import ru.skatelab.capture.domain.usecase.StopStreamingUseCase
import ru.skatelab.capture.presentation.SessionState

class CalibrationViewModelTest {
    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)

    private lateinit var calibrateUseCase: CalibrateSensorUseCase
    private lateinit var startStreamingUseCase: StartStreamingUseCase
    private lateinit var stopStreamingUseCase: StopStreamingUseCase
    private lateinit var bleRepository: BleRepository
    private lateinit var sessionState: SessionState
    private lateinit var viewModel: CalibrationViewModel

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)

        calibrateUseCase = mockk()
        startStreamingUseCase = mockk(relaxed = true)
        stopStreamingUseCase = mockk(relaxed = true)
        bleRepository = mockk(relaxed = true)
        sessionState = SessionState()

        every { bleRepository.imuSamples } returns emptyFlow()
        coEvery { startStreamingUseCase.invoke(any()) } returns Result.success(Unit)
        coEvery { stopStreamingUseCase.invoke(any()) } returns Result.success(Unit)

        viewModel = CalibrationViewModel(calibrateUseCase, startStreamingUseCase, stopStreamingUseCase, bleRepository, sessionState)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun calibrateBoth_setsBothCalibrations() =
        testScope.runTest {
            val leftData = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)
            val rightData = CalibrationData(floatArrayOf(0f, 1f, 0f, 0f), 2000L)
            coEvery { calibrateUseCase.invoke(any()) } returns
                Result.success(
                    mapOf(SensorId.LEFT to leftData, SensorId.RIGHT to rightData),
                )

            viewModel.calibrateBoth()
            runCurrent()

            assertEquals(leftData, viewModel.leftCalibration.value)
            assertEquals(rightData, viewModel.rightCalibration.value)
            assertNull(viewModel.error.value)
        }

    @Test
    fun calibrateBoth_failure_setsError() =
        testScope.runTest {
            coEvery { calibrateUseCase.invoke(any()) } returns
                Result.failure(IllegalStateException("No still samples"))

            viewModel.calibrateBoth()
            runCurrent()

            assertNull(viewModel.leftCalibration.value)
            assertNull(viewModel.rightCalibration.value)
            assertTrue(viewModel.error.value!!.contains("No still samples"))
        }

    @Test
    fun calibrateBoth_updatesSessionState() =
        testScope.runTest {
            val leftData = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)
            val rightData = CalibrationData(floatArrayOf(0f, 1f, 0f, 0f), 2000L)
            coEvery { calibrateUseCase.invoke(any()) } returns
                Result.success(
                    mapOf(SensorId.LEFT to leftData, SensorId.RIGHT to rightData),
                )

            viewModel.calibrateBoth()
            runCurrent()

            val cal = sessionState.calibration
            assertEquals(leftData, cal[SensorId.LEFT])
            assertEquals(rightData, cal[SensorId.RIGHT])
        }

    @Test
    fun isCalibrating_resetsAfterCompletion() =
        testScope.runTest {
            coEvery { calibrateUseCase.invoke(any()) } returns
                Result.success(
                    mapOf(SensorId.LEFT to CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)),
                )

            viewModel.calibrateBoth()
            assertFalse(viewModel.isCalibrating.value)

            runCurrent()
            assertFalse(viewModel.isCalibrating.value)
        }

    @Test
    fun startPreview_callsStartStreaming() =
        testScope.runTest {
            viewModel.startPreview(SensorId.LEFT)
            runCurrent()

            coVerify { startStreamingUseCase.invoke(SensorId.LEFT) }
        }

    @Test
    fun stopPreview_callsStopStreaming() =
        testScope.runTest {
            coEvery { startStreamingUseCase.invoke(SensorId.LEFT) } returns Result.success(Unit)
            coEvery { stopStreamingUseCase.invoke(SensorId.LEFT) } returns Result.success(Unit)

            viewModel.startPreview(SensorId.LEFT)
            testDispatcher.scheduler.runCurrent()

            viewModel.stopPreview()
            testDispatcher.scheduler.runCurrent()

            coVerify(timeout = 2000L) { stopStreamingUseCase.invoke(SensorId.LEFT) }
        }

    @Test
    fun calibrateBoth_partialResult_setsAvailableCalibrations() =
        testScope.runTest {
            val leftData = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)
            coEvery { calibrateUseCase.invoke(any()) } returns
                Result.success(
                    mapOf(SensorId.LEFT to leftData),
                )

            viewModel.calibrateBoth()
            runCurrent()

            assertEquals(leftData, viewModel.leftCalibration.value)
            assertNull(viewModel.rightCalibration.value)
        }
}
