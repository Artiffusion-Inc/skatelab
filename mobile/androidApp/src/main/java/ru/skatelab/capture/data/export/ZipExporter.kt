package ru.skatelab.capture.data.export

import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.File
import java.io.FileInputStream
import java.util.zip.CRC32
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import javax.inject.Inject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.service.SessionExporter

/**
 * Exports a [CaptureSession] as a ZIP archive containing:
 * - MP4 video file
 * - Left IMU .binpb file
 * - Right IMU .binpb file
 * - Frame timestamps CSV file
 * - Manifest JSON file
 */
class ZipExporter
    @Inject
    constructor() : SessionExporter {
        companion object {
            private const val BUFFER_SIZE = 16_384

            // STORED requires size/crc pre-computation. Safe for atomically-written binpb,
            // but MP4 is excluded because it may still be finalizing when export runs.
            private val STORED_EXTENSIONS = setOf("binpb")
        }

        /**
         * Export a capture session to a ZIP file.
         * @param session the capture session with file references
         * @param zipFile the output ZIP file
         */
        override suspend fun export(
            session: CaptureSession,
            zipFile: File,
        ) = withContext(Dispatchers.IO) {
            val entries =
                listOf(
                    session.videoFile,
                    session.imuLeftFile,
                    session.imuRightFile,
                    session.frameTimestampsFile,
                    session.manifestFile,
                )

            // Atomic write: write to temp file first, then rename to final destination
            val tempFile = File(zipFile.path + ".tmp")
            ZipOutputStream(BufferedOutputStream(tempFile.outputStream(), BUFFER_SIZE)).use { zos ->
                entries.forEach { file ->
                    if (file.exists()) {
                        addToZip(zos, file)
                    }
                }
            }
            if (!tempFile.renameTo(zipFile)) {
                tempFile.delete()
                throw java.io.IOException("Failed to rename temp ZIP to ${zipFile.absolutePath}")
            }
        }

        private fun addToZip(
            zos: ZipOutputStream,
            file: File,
        ) {
            val entry = ZipEntry(file.name)
            if (file.extension in STORED_EXTENSIONS) {
                entry.method = ZipEntry.STORED
                entry.size = file.length()
                entry.compressedSize = file.length()
                entry.setCrc(computeCrc32(file))
            }
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

        private fun computeCrc32(file: File): Long {
            val crc = CRC32()
            BufferedInputStream(FileInputStream(file), BUFFER_SIZE).use { fis ->
                val buffer = ByteArray(BUFFER_SIZE)
                var read: Int
                while (fis.read(buffer).also { read = it } != -1) {
                    crc.update(buffer, 0, read)
                }
            }
            return crc.value
        }
    }
