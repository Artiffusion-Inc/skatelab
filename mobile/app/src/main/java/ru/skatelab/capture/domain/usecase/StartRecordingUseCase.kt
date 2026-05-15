package ru.skatelab.capture.domain.usecase

import java.io.File
import javax.inject.Inject
import javax.inject.Named
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository

class StartRecordingUseCase
    @Inject
    constructor(
        private val bleRepository: BleRepository,
        private val cameraRepository: CameraRepository,
        @Named("clockNanos") private val clockNanos: () -> Long,
    ) {
        suspend operator fun invoke(
            outputDir: File,
            videoFile: File,
            framesFile: File,
            imuLeftFile: File,
            imuRightFile: File,
        ): Result<RecordingStartInfo> =
            runCatching {
                val tImuStartSentNs = clockNanos()

                val (leftResult, rightResult, cameraResult) =
                    coroutineScope {
                        val left = async(Dispatchers.IO) { bleRepository.startStreaming(SensorId.LEFT) }
                        val right = async(Dispatchers.IO) { bleRepository.startStreaming(SensorId.RIGHT) }
                        val cameraDeferred =
                            async(Dispatchers.IO) {
                                cameraRepository.startRecording(videoFile, framesFile)
                            }
                        Triple(left.await(), right.await(), cameraDeferred.await())
                    }
                if (leftResult.isFailure || rightResult.isFailure) {
                    val leftErr = leftResult.exceptionOrNull()?.message
                    val rightErr = rightResult.exceptionOrNull()?.message
                    throw Exception("BLE streaming start failed: L=$leftErr, R=$rightErr")
                }
                val cameraData = cameraResult.getOrThrow()

                val imuStartDelayMs =
                    mapOf(
                        SensorId.LEFT to ((cameraData.tFirstFrameNs - tImuStartSentNs) / 1_000_000),
                        SensorId.RIGHT to ((cameraData.tFirstFrameNs - tImuStartSentNs) / 1_000_000),
                    )

                RecordingStartInfo(
                    t0Ns = cameraData.tFirstFrameNs,
                    timestampSource = cameraData.timestampSource,
                    videoStartDelayMs = cameraData.videoStartDelayMs,
                    imuStartDelayMs = imuStartDelayMs,
                    videoFile = videoFile,
                    imuLeftFile = imuLeftFile,
                    imuRightFile = imuRightFile,
                    framesFile = framesFile,
                )
            }
    }

data class RecordingStartInfo(
    val t0Ns: Long,
    val timestampSource: String,
    val videoStartDelayMs: Long,
    val imuStartDelayMs: Map<SensorId, Long>,
    val videoFile: File,
    val imuLeftFile: File,
    val imuRightFile: File,
    val framesFile: File,
)