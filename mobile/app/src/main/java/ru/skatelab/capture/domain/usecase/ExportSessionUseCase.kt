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
        val imuDelayEntries = session.imuStartDelayMs.entries.joinToString(",") { (k, v) ->
            "\"${k.name}\": $v"
        }
        val calEntries = session.calibration.entries.joinToString(",") { (sensorId, calib) ->
            "\"${sensorId.name}\": {\"quatRef\": [${calib.quatRef.joinToString(",")}],\"calibratedAt\": ${calib.calibratedAt}}"
        }
        return buildString {
            appendLine("{")
            appendLine("  \"sessionId\": \"${session.id}\",")
            appendLine("  \"t0Ns\": ${session.t0Ns},")
            appendLine("  \"durationMs\": ${session.durationMs},")
            appendLine("  \"videoFps\": ${session.videoFps},")
            appendLine("  \"timestampSource\": \"${session.timestampSource}\",")
            appendLine("  \"videoStartDelayMs\": ${session.videoStartDelayMs},")
            appendLine("  \"imuStartDelayMs\": {$imuDelayEntries},")
            appendLine("  \"calibration\": {$calEntries},")
            appendLine("  \"createdAt\": ${session.createdAt},")
            appendLine("  \"isComplete\": ${session.isComplete}")
            append("}")
        }
    }
}
