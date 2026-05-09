package ru.skatelab.capture.domain.usecase

import ru.skatelab.capture.data.export.ZipExporter
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.model.SensorId
import java.io.File
import javax.inject.Inject

class ExportSessionUseCase @Inject constructor(
    private val zipExporter: ZipExporter,
) {
    fun invoke(session: CaptureSession, outputZip: File): Result<File> = runCatching {
        // Build manifest JSON
        val manifest = buildManifest(session)
        val manifestFile = File(session.videoFile.parentFile, "manifest.json")
        manifestFile.writeText(manifest)

        // Update session manifest file reference
        val sessionWithManifest = session.copy(manifestFile = manifestFile)

        // Export ZIP
        zipExporter.export(sessionWithManifest, outputZip)

        outputZip
    }

    private fun buildManifest(session: CaptureSession): String {
        return buildString {
            appendLine("{")
            appendLine("  \"sessionId\": \"${session.id}\",")
            appendLine("  \"t0Ns\": ${session.t0Ns},")
            appendLine("  \"durationMs\": ${session.durationMs},")
            appendLine("  \"videoFps\": ${session.videoFps},")
            appendLine("  \"timestampSource\": \"${session.timestampSource}\",")
            appendLine("  \"videoStartDelayMs\": ${session.videoStartDelayMs},")
            appendLine("  \"imuStartDelayMs\": {")
            appendLine("    \"LEFT\": ${session.imuStartDelayMs[SensorId.LEFT]},")
            appendLine("    \"RIGHT\": ${session.imuStartDelayMs[SensorId.RIGHT]}")
            appendLine("  },")
            appendLine("  \"calibration\": {")
            session.calibration.forEach { (sensorId, calib) ->
                appendLine("    \"${sensorId.name}\": {")
                appendLine("      \"quatRef\": [${calib.quatRef.joinToString(", ")}],")
                appendLine("      \"calibratedAt\": ${calib.calibratedAt}")
                appendLine("    },")
            }
            appendLine("  },")
            appendLine("  \"createdAt\": ${session.createdAt},")
            appendLine("  \"isComplete\": ${session.isComplete}")
            append("}")
        }
    }
}
