package ru.skatelab.capture.presentation.calibration

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
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

class CalibrationViewModelTest {

    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)

    private lateinit var calibrateUseCase: CalibrateSensorUseCase
    private lateinit var bleRepository: BleRepository
    private lateinit var viewModel: CalibrationViewModel

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)

        calibrateUseCase = mockk()
        bleRepository = mockk(relaxed = true)

        every { bleRepository.imuSamples } returns emptyFlow()
        coEvery { bleRepository.startStreaming(any()) } returns Result.success(Unit)
        coEvery { bleRepository.stopStreaming(any()) } returns Result.success(Unit)

        viewModel = CalibrationViewModel(calibrateUseCase, bleRepository)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun calibrateLeft_setsLeftCalibration() = testScope.runTest {
        val data = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)
        coEvery { calibrateUseCase.invoke(SensorId.LEFT) } returns Result.success(data)

        viewModel.calibrate(SensorId.LEFT)
        advanceUntilIdle()

        assertEquals(data, viewModel.leftCalibration.value)
        assertNull(viewModel.error.value)
    }

    @Test
    fun calibrateRight_setsRightCalibration() = testScope.runTest {
        val data = CalibrationData(floatArrayOf(0f, 1f, 0f, 0f), 2000L)
        coEvery { calibrateUseCase.invoke(SensorId.RIGHT) } returns Result.success(data)

        viewModel.calibrate(SensorId.RIGHT)
        advanceUntilIdle()

        assertEquals(data, viewModel.rightCalibration.value)
        assertNull(viewModel.error.value)
    }

    @Test
    fun calibrateFailure_setsError() = testScope.runTest {
        coEvery { calibrateUseCase.invoke(SensorId.LEFT) } returns
            Result.failure(IllegalStateException("No still samples"))

        viewModel.calibrate(SensorId.LEFT)
        advanceUntilIdle()

        assertNull(viewModel.leftCalibration.value)
        assertTrue(viewModel.error.value!!.contains("No still samples"))
    }

    @Test
    fun calibrate_updatesSessionState() = testScope.runTest {
        val data = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)
        coEvery { calibrateUseCase.invoke(SensorId.LEFT) } returns Result.success(data)

        viewModel.calibrate(SensorId.LEFT)
        advanceUntilIdle()

        assertTrue(ru.skatelab.capture.presentation.SessionState.calibration.containsKey(SensorId.LEFT))
    }

    @Test
    fun isCalibrating_resetsAfterCompletion() = testScope.runTest {
        coEvery { calibrateUseCase.invoke(SensorId.LEFT) } returns
            Result.success(CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L))

        viewModel.calibrate(SensorId.LEFT)
        assertFalse(viewModel.isCalibrating.value) // not yet started in test dispatcher

        advanceUntilIdle()
        assertFalse(viewModel.isCalibrating.value)
    }

    @Test
    fun startPreview_callsStartStreaming() = testScope.runTest {
        viewModel.startPreview(SensorId.LEFT)
        advanceUntilIdle()

        coVerify { bleRepository.startStreaming(SensorId.LEFT) }
    }

    @Test
    fun stopPreview_callsStopStreaming() = testScope.runTest {
        coEvery { bleRepository.startStreaming(SensorId.LEFT) } returns Result.success(Unit)
        coEvery { bleRepository.stopStreaming(SensorId.LEFT) } returns Result.success(Unit)

        viewModel.startPreview(SensorId.LEFT)
        testDispatcher.scheduler.advanceUntilIdle()

        viewModel.stopPreview()
        testDispatcher.scheduler.advanceUntilIdle()

        coVerify(timeout = 2000L) { bleRepository.stopStreaming(SensorId.LEFT) }
    }

    @Test
    fun calibrateLeft_thenRight_bothStored() = testScope.runTest {
        val leftData = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)
        val rightData = CalibrationData(floatArrayOf(0f, 1f, 0f, 0f), 2000L)
        coEvery { calibrateUseCase.invoke(SensorId.LEFT) } returns Result.success(leftData)
        coEvery { calibrateUseCase.invoke(SensorId.RIGHT) } returns Result.success(rightData)

        viewModel.calibrate(SensorId.LEFT)
        advanceUntilIdle()
        viewModel.calibrate(SensorId.RIGHT)
        advanceUntilIdle()

        assertEquals(leftData, viewModel.leftCalibration.value)
        assertEquals(rightData, viewModel.rightCalibration.value)
        assertEquals(2, ru.skatelab.capture.presentation.SessionState.calibration.size)
    }
}
