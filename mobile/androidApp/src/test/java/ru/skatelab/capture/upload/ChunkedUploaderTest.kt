package ru.skatelab.capture.upload

import io.mockk.mockk
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import ru.skatelab.shared.models.CompletedPart
import ru.skatelab.shared.models.UploadInitResponse
import ru.skatelab.shared.models.UploadPart

class ChunkedUploaderTest {
    @get:Rule
    val tempFolder = TemporaryFolder()

    private lateinit var uploader: ChunkedUploader

    @Before
    fun setUp() {
        uploader = ChunkedUploader(mockk(relaxed = true), mockk(relaxed = true))
    }

    // --- readFileChunk tests ---

    @Test
    fun readFileChunk_readsFullFile() {
        val file = tempFolder.newFile("test.bin")
        val data = byteArrayOf(1, 2, 3, 4, 5)
        file.writeBytes(data)

        val chunk = uploader.readFileChunk(file, 0, 5)
        assertArrayEquals(data, chunk)
    }

    @Test
    fun readFileChunk_readsMiddleSection() {
        val file = tempFolder.newFile("test.bin")
        val data = byteArrayOf(0, 1, 2, 3, 4, 5, 6, 7, 8, 9)
        file.writeBytes(data)

        val chunk = uploader.readFileChunk(file, 3, 7)
        assertArrayEquals(byteArrayOf(3, 4, 5, 6), chunk)
    }

    @Test
    fun readFileChunk_singleByte() {
        val file = tempFolder.newFile("test.bin")
        val data = byteArrayOf(42)
        file.writeBytes(data)

        val chunk = uploader.readFileChunk(file, 0, 1)
        assertEquals(1, chunk.size)
        assertEquals(42.toByte(), chunk[0])
    }

    @Test
    fun readFileChunk_largeFile_offsetRead() {
        val file = tempFolder.newFile("large.bin")
        val data = ByteArray(10000) { (it % 256).toByte() }
        file.writeBytes(data)

        val chunk = uploader.readFileChunk(file, 5000L, 5010L)
        assertEquals(10, chunk.size)
        assertEquals((5000 % 256).toByte(), chunk[0])
    }

    // --- Model tests ---

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

    // --- Serialization round-trip tests ---

    @Test
    fun completedPart_serialization_roundTrip() {
        val json = kotlinx.serialization.json.Json
        val original = CompletedPart(5, "etag-xyz")
        val encoded =
            json.encodeToString(
                ru.skatelab.shared.models.CompletedPart
                    .serializer(),
                original,
            )
        val decoded =
            json.decodeFromString(
                ru.skatelab.shared.models.CompletedPart
                    .serializer(),
                encoded,
            )
        assertEquals(original, decoded)
    }

    @Test
    fun uploadInitResponse_serialization_roundTrip() {
        val json = kotlinx.serialization.json.Json
        val original =
            UploadInitResponse(
                uploadId = "up-rt",
                key = "videos/rt.mp4",
                chunkSize = 5_242_880,
                partCount = 2,
                parts = listOf(UploadPart(1, "https://r2.example.com/p1"), UploadPart(2, "https://r2.example.com/p2")),
            )
        val encoded = json.encodeToString(UploadInitResponse.serializer(), original)
        val decoded = json.decodeFromString(UploadInitResponse.serializer(), encoded)
        assertEquals(original, decoded)
    }

    @Test
    fun uploadPart_serialization_snakeCaseKeys() {
        val json = kotlinx.serialization.json.Json { prettyPrint = false }
        val part = UploadPart(3, "https://example.com")
        val encoded = json.encodeToString(UploadPart.serializer(), part)
        assertTrue("Should use snake_case key", encoded.contains("part_number"))
    }
}
