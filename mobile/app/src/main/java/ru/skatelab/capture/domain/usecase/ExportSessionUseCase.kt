package ru.skatelab.capture.domain.usecase

import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import javax.inject.Inject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.service.ManifestWriter
import ru.skatelab.capture.domain.service.SessionExporter

class ExportSessionUseCase
    @Inject
    constructor(
        private val sessionExporter: SessionExporter,
        private val manifestBuilder: ManifestWriter,
    ) {
        suspend fun invoke(
            session: CaptureSession,
            outputZip: File,
        ): Result<File> =
            withContext(Dispatchers.IO) {
                runCatching {
                    // Build manifest JSON
                    val manifest = buildManifest(session)
                    val manifestFile = File(session.videoFile.parentFile, "manifest.json")
                    manifestFile.writeText(manifest)

                    // Update session manifest file reference
                    val sessionWithManifest = session.copy(manifestFile = manifestFile)

                    // Export ZIP
                    sessionExporter.export(sessionWithManifest, outputZip)

                    outputZip
                }
            }

        private fun buildManifest(session: CaptureSession): String =
            manifestBuilder.apply {
                version("2.0")
                t0Ns(session.t0Ns)
                durationMs(session.durationMs)
                video {
                    filename(session.videoFile.name)
                    fps(session.actualFps)
                    width(session.videoWidth)
                    height(session.videoHeight)
                    actualFpsVerified(session.fpsVerified)
                    timestampSource(session.timestampSource)
                    videoStartDelayMs(session.videoStartDelayMs)
                    frameTimestampsFile(session.frameTimestampsFile.name)
                    firstFrameNs(session.firstFrameNs)
                }
                imu("left") {
                    filename(session.imuLeftFile.name)
                    sensorId(SensorId.LEFT.name)
                    clockOffsetNs(session.clockOffsetNs[SensorId.LEFT] ?: 0L)
                    imuStartDelayMs(session.imuStartDelayMs[SensorId.LEFT] ?: 0L)
                }
                imu("right") {
                    filename(session.imuRightFile.name)
                    sensorId(SensorId.RIGHT.name)
                    clockOffsetNs(session.clockOffsetNs[SensorId.RIGHT] ?: 0L)
                    imuStartDelayMs(session.imuStartDelayMs[SensorId.RIGHT] ?: 0L)
                }
                calibration {
                    val leftCal = session.calibration[SensorId.LEFT]
                    if (leftCal != null) {
                        left(leftCal.quatRef, leftCal.calibratedAt.toString())
                    }
                    val rightCal = session.calibration[SensorId.RIGHT]
                    if (rightCal != null) {
                        right(rightCal.quatRef, rightCal.calibratedAt.toString())
                    }
                }
                createdAt(formatIso8601(session.createdAt))
            }.build()

        private fun formatIso8601(epochMs: Long): String {
            val sdf = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US)
            sdf.timeZone = TimeZone.getTimeZone("UTC")
            return sdf.format(Date(epochMs))
        }
    }
