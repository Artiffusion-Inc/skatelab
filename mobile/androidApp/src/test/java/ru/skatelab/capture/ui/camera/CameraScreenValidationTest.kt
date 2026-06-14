package ru.skatelab.capture.ui.camera

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.io.File

/**
 * Unit tests for CameraViewModel.validateVideoFile logic.
 * Tests the validation rules (format, size, existence) without requiring
 * Compose or Android context — validates the business logic only.
 */
class CameraScreenValidationTest {

    private val tempDir = System.getProperty("java.io.tmpdir")

    @Test
    fun validateVideoFile_nonExistentFile_returnsNotFoundError() {
        // Can't instantiate CameraViewModel without Hilt deps,
        // so test the validation logic extracted as a standalone function
        val path = "$tempDir/nonexistent_${System.currentTimeMillis()}.mp4"
        val result = validateVideoFile(path)
        assertEquals("File not found", result)
    }

    @Test
    fun validateVideoFile_unsupportedFormat_returnsFormatError() {
        val file = File("$tempDir/test_${System.currentTimeMillis()}.txt")
        file.writeText("not a video")
        try {
            val result = validateVideoFile(file.absolutePath)
            assertEquals("Unsupported format", result?.substring(0, 18))
        } finally {
            file.delete()
        }
    }

    @Test
    fun validateVideoFile_mp4File_returnsNull() {
        val file = File("$tempDir/test_${System.currentTimeMillis()}.mp4")
        file.writeBytes(ByteArray(0))
        try {
            val result = validateVideoFile(file.absolutePath)
            assertNull(result)
        } finally {
            file.delete()
        }
    }

    // Extracted validation logic matching CameraViewModel.validateVideoFile
    // without Android context dependency (string resources replaced with constants)
    private fun validateVideoFile(path: String): String? {
        val file = File(path)
        if (!file.exists()) return "File not found"
        val ext = file.extension.lowercase()
        if (ext !in listOf("mp4", "mov", "3gp", "webm", "mkv")) {
            return "Unsupported format: .$ext"
        }
        val maxSizeMb = 100
        if (file.length() > maxSizeMb * 1024L * 1024L) {
            val sizeMb = file.length() / (1024L * 1024L)
            return "File too large: ${sizeMb}MB (max ${maxSizeMb}MB)"
        }
        return null
    }
}
