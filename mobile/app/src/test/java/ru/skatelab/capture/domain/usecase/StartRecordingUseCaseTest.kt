package ru.skatelab.capture.domain.usecase

import io.mockk.coEvery
import io.mockk.mockk
import java.io.File
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository

class StartRecordingUseCaseTest {
    private lateinit var bleRepository: BleRepository
    private lateinit var cameraRepository: CameraRepository
    private lateinit var useCase: StartRecordingUseCase

    private val outputDir = File("/tmp/test-output")
    private val videoFile = File(outputDir, "video.mp4")
    private val framesFile = File(outputDir, "frames.csv")
    private val imuLeftFile = File(outputDir, "imu_left.binpb")
    private val imuRightFile = File(outputDir, "imu_right.binpb")

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        cameraRepository = mockk(relaxed = true)

        useCase = StartRecordingUseCase(bleRepository, cameraRepository) { 0L }
    }

    @Test
    fun successfulStart_returnsRecordingStartInfo() =
        runTest {
            coEvery { bleRepository.startStreaming(SensorId.LEFT) } returns Result.success(Unit)
            coEvery { bleRepository.startStreaming(SensorId.RIGHT) } returns Result.success(Unit)
            coEvery { cameraRepository.startRecording(videoFile, framesFile) } returns
                Result.success(
                    CameraRepository.RecordingStartResult(
                        tStartCalledNs = 1_000_000_000L,
                        tFirstFrameNs = 1_000_050_000L,
                        timestampSource = "SENSOR",
                        videoStartDelayMs = 50L,
                    ),
                )

            val result = useCase.invoke(outputDir, videoFile, framesFile, imuLeftFile, imuRightFile)

            assertTrue(result.isSuccess)
            val info = result.getOrThrow()
            assertEquals(1_000_050_000L, info.t0Ns)
            assertEquals("SENSOR", info.timestampSource)
            assertEquals(50L, info.videoStartDelayMs)
            assertEquals(videoFile, info.videoFile)
            assertEquals(imuLeftFile, info.imuLeftFile)
            assertEquals(imuRightFile, info.imuRightFile)
            assertEquals(framesFile, info.framesFile)
        }

    @Test
    fun bleStreamingLeftFailure_returnsFailure() =
        runTest {
            coEvery { bleRepository.startStreaming(SensorId.LEFT) } returns
                Result.failure(IllegalStateException("BLE left failed"))
            coEvery { bleRepository.startStreaming(SensorId.RIGHT) } returns Result.success(Unit)

            val result = useCase.invoke(outputDir, videoFile, framesFile, imuLeftFile, imuRightFile)

            assertTrue(result.isFailure)
        }

    @Test
    fun bleStreamingRightFailure_returnsFailure() =
        runTest {
            coEvery { bleRepository.startStreaming(SensorId.LEFT) } returns Result.success(Unit)
            coEvery { bleRepository.startStreaming(SensorId.RIGHT) } returns
                Result.failure(IllegalStateException("BLE right failed"))

            val result = useCase.invoke(outputDir, videoFile, framesFile, imuLeftFile, imuRightFile)

            assertTrue(result.isFailure)
        }

    @Test
    fun cameraStartFailure_returnsFailure() =
        runTest {
            coEvery { bleRepository.startStreaming(SensorId.LEFT) } returns Result.success(Unit)
            coEvery { bleRepository.startStreaming(SensorId.RIGHT) } returns Result.success(Unit)
            coEvery { cameraRepository.startRecording(any(), any()) } returns
                Result.failure(IllegalStateException("Camera failed"))

            val result = useCase.invoke(outputDir, videoFile, framesFile, imuLeftFile, imuRightFile)

            assertTrue(result.isFailure)
        }

    @Test
    fun imuStartDelayCalculatedCorrectly() =
        runTest {
            val tFirstFrameNs = 150_000_000L

            coEvery { bleRepository.startStreaming(SensorId.LEFT) } returns Result.success(Unit)
            coEvery { bleRepository.startStreaming(SensorId.RIGHT) } returns Result.success(Unit)
            coEvery { cameraRepository.startRecording(any(), any()) } returns
                Result.success(
                    CameraRepository.RecordingStartResult(
                        tStartCalledNs = 100_000_000L,
                        tFirstFrameNs = tFirstFrameNs,
                        timestampSource = "BOOTTIME",
                        videoStartDelayMs = 50L,
                    ),
                )

            val result = useCase.invoke(outputDir, videoFile, framesFile, imuLeftFile, imuRightFile)

            assertTrue(result.isSuccess)
            val info = result.getOrThrow()
            val expectedDelayMs = (tFirstFrameNs - 0L) / 1_000_000
            assertEquals(expectedDelayMs, info.imuStartDelayMs[SensorId.LEFT])
            assertEquals(expectedDelayMs, info.imuStartDelayMs[SensorId.RIGHT])
        }
}
