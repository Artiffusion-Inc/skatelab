package ru.skatelab.capture.upload

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import ru.skatelab.shared.api.UploadsApi
import ru.skatelab.shared.models.UploadInitResponse
import ru.skatelab.shared.models.UploadPart

class ChunkedUploaderTest {
    @get:Rule
    val tempFolder = TemporaryFolder()

    private lateinit var uploadsApi: UploadsApi
    private lateinit var httpClient: HttpClient

    private val stubInit =
        UploadInitResponse(
            uploadId = "up-1",
            key = "videos/test.mp4",
            chunkSize = 5_242_880,
            partCount = 1,
            parts = listOf(UploadPart(1, "https://r2.example.com/p1")),
        )

    @Before
    fun setUp() {
        uploadsApi = mockk(relaxed = true)
        val mockEngine =
            MockEngine { request ->
                respond(
                    "",
                    status = HttpStatusCode.OK,
                    headers = headersOf(HttpHeaders.ETag, "\"etag-1\""),
                )
            }
        httpClient = HttpClient(mockEngine)
    }

    @Test
    fun upload_smallFile_completesSuccessfully() =
        runTest {
            val file = tempFolder.newFile("test.mp4").also { it.writeBytes(ByteArray(100) { it.toByte() }) }

            coEvery { uploadsApi.init("test.mp4", "video/mp4", 100) } returns stubInit
            coEvery { uploadsApi.complete("up-1", "videos/test.mp4", any()) } returns Unit

            val uploader = ChunkedUploader(uploadsApi, httpClient)
            val key = uploader.upload(file, "test.mp4")

            assertEquals("videos/test.mp4", key)
        }

    @Test
    fun upload_reportsProgress() =
        runTest {
            val file = tempFolder.newFile("test.mp4").also { it.writeBytes(ByteArray(200) { it.toByte() }) }

            val multiPartInit =
                stubInit.copy(
                    chunkSize = 100,
                    partCount = 2,
                    parts =
                        listOf(
                            UploadPart(1, "https://r2.example.com/p1"),
                            UploadPart(2, "https://r2.example.com/p2"),
                        ),
                )
            coEvery { uploadsApi.init(any(), any(), any()) } returns multiPartInit
            coEvery { uploadsApi.complete(any(), any(), any()) } returns Unit

            val progressCalls = mutableListOf<Pair<Long, Long>>()
            val uploader = ChunkedUploader(uploadsApi, httpClient)
            uploader.upload(file, "progress.mp4", onProgress = { uploaded, total ->
                progressCalls.add(uploaded to total)
            })

            assertTrue(progressCalls.isNotEmpty())
            assertEquals(200L, progressCalls.last().first)
        }

    @Test
    fun upload_partUploadFails_throwsUploadException() =
        runTest {
            val file = tempFolder.newFile("test.mp4").also { it.writeBytes(ByteArray(50) { it.toByte() }) }

            coEvery { uploadsApi.init(any(), any(), any()) } returns stubInit

            val failEngine =
                MockEngine { request ->
                    respond("Internal Server Error", status = HttpStatusCode.InternalServerError)
                }
            val failClient = HttpClient(failEngine)

            val uploader = ChunkedUploader(uploadsApi, failClient)

            try {
                uploader.upload(file, "fail.mp4")
                throw AssertionError("Expected UploadException")
            } catch (e: UploadException) {
                assertTrue(e.message!!.contains("Part upload failed"))
            }
        }
}
