package ru.skatelab.capture.data.export

import ru.skatelab.capture.domain.model.CaptureSession
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.File
import java.io.FileInputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import javax.inject.Inject

/**
 * Exports a [CaptureSession] as a ZIP archive containing:
 * - MP4 video file
 * - Left IMU .binpb file
 * - Right IMU .binpb file
 * - Frame timestamps CSV file
 * - Manifest JSON file
 */
class ZipExporter @Inject constructor() {

    companion object {
        private const val BUFFER_SIZE = 16_384
    }

    /**
     * Export a capture session to a ZIP file.
     * @param session the capture session with file references
     * @param zipFile the output ZIP file
     */
    fun export(session: CaptureSession, zipFile: File) {
        val entries = listOf(
            session.videoFile,
            session.imuLeftFile,
            session.imuRightFile,
            session.frameTimestampsFile,
            session.manifestFile,
        )

        ZipOutputStream(BufferedOutputStream(zipFile.outputStream(), BUFFER_SIZE)).use { zos ->
            entries.forEach { file ->
                if (file.exists()) {
                    addToZip(zos, file)
                }
            }
        }
    }

    private fun addToZip(zos: ZipOutputStream, file: File) {
        val entry = ZipEntry(file.name)
        zos.putNextEntry(entry)
        BufferedInputStream(FileInputStream(file), BUFFER_SIZE).use { fis ->
            val buffer = ByteArray(BUFFER_SIZE)
            var read: Int
            while (fis.read(buffer).also { read = it } != -1) {
                zos.write(buffer, 0, read)
            }
        }
        zos.closeEntry()
    }
}
