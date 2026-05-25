package ru.skatelab.capture.upload

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import ru.skatelab.shared.models.CompletedPart
import ru.skatelab.shared.models.UploadInitResponse
import ru.skatelab.shared.models.UploadPart

class ChunkedUploaderTest {
    @Test
    fun uploadInitResponse_hasCorrectFields() {
        val init =
            UploadInitResponse(
                uploadId = "up-1",
                key = "videos/test.mp4",
                chunkSize = 5_242_880,
                partCount = 3,
                parts =
                    listOf(
                        UploadPart(1, "https://r2.example.com/p1"),
                        UploadPart(2, "https://r2.example.com/p2"),
                        UploadPart(3, "https://r2.example.com/p3"),
                    ),
            )
        assertEquals("up-1", init.uploadId)
        assertEquals("videos/test.mp4", init.key)
        assertEquals(5_242_880, init.chunkSize)
        assertEquals(3, init.partCount)
        assertEquals(3, init.parts.size)
    }

    @Test
    fun uploadPart_hasCorrectFields() {
        val part = UploadPart(2, "https://r2.example.com/p2")
        assertEquals(2, part.partNumber)
        assertEquals("https://r2.example.com/p2", part.url)
    }

    @Test
    fun completedPart_hasCorrectFields() {
        val part = CompletedPart(2, "etag-abc")
        assertEquals(2, part.partNumber)
        assertEquals("etag-abc", part.etag)
    }

    @Test
    fun uploadException_containsMessage() {
        val ex = UploadException("Part upload failed: 500")
        assertTrue(ex.message!!.contains("Part upload failed"))
    }

    @Test
    fun uploadInitResponse_singlePart() {
        val init =
            UploadInitResponse(
                uploadId = "up-2",
                key = "videos/small.mp4",
                chunkSize = 8_388_608,
                partCount = 1,
                parts = listOf(UploadPart(1, "https://r2.example.com/p1")),
            )
        assertEquals(1, init.partCount)
        assertEquals(1, init.parts.size)
    }

    @Test
    fun uploadException_isException_subclass() {
        val ex = UploadException("test")
        assertTrue(ex is Exception)
    }

    @Test
    fun completedPart_partNumber_ordering() {
        val parts =
            listOf(
                CompletedPart(3, "e3"),
                CompletedPart(1, "e1"),
                CompletedPart(2, "e2"),
            )
        val sorted = parts.sortedBy { it.partNumber }
        assertEquals(listOf(1, 2, 3), sorted.map { it.partNumber })
    }

    @Test
    fun uploadInitResponse_largeFile_noTruncation() {
        val largeChunkSize = 5_242_880
        val init =
            UploadInitResponse(
                uploadId = "up-big",
                key = "videos/large.mp4",
                chunkSize = largeChunkSize,
                partCount = 400,
                parts = (1..400).map { UploadPart(it, "https://r2.example.com/p$it") },
            )
        assertEquals(400, init.parts.size)
        assertEquals(largeChunkSize, init.chunkSize)
    }
}
