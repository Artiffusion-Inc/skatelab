package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import ru.skatelab.shared.models.CompletedPart
import kotlin.test.Test
import kotlin.test.assertEquals

class UploadsApiTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun init_returnsUploadInitResponse() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            respond(
                """{"upload_id":"up-1","key":"videos/test.mp4","chunk_size":5242880,"part_count":3,"parts":[{"part_number":1,"url":"https://r2.example.com/p1"},{"part_number":2,"url":"https://r2.example.com/p2"},{"part_number":3,"url":"https://r2.example.com/p3"}]}""",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val api = UploadsApi(client)
        val response = api.init("test.mp4", "video/mp4", 10_000_000)
        assertEquals("up-1", response.uploadId)
        assertEquals("videos/test.mp4", response.key)
        assertEquals(5242880, response.chunkSize)
        assertEquals(3, response.partCount)
        assertEquals(3, response.parts.size)
        assertEquals(1, response.parts[0].partNumber)
        assertEquals("https://r2.example.com/p1", response.parts[0].url)
    }

    @Test
    fun init_sendsQueryParameters() = kotlinx.coroutines.test.runTest {
        var capturedUrl: String? = null
        val engine = MockEngine { request ->
            capturedUrl = request.url.toString()
            respond(
                """{"upload_id":"up-2","key":"k","chunk_size":1024,"part_count":1,"parts":[]}""",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val api = UploadsApi(client)
        api.init("file.bin", "application/octet-stream", 500)
        val url = capturedUrl!!
        assert(url.contains("file_name=file.bin"))
        assert(url.contains("content_type=application%2Foctet-stream"))
        assert(url.contains("total_size=500"))
    }

    @Test
    fun complete_postsToCompleteEndpoint() = kotlinx.coroutines.test.runTest {
        var requestPath: String? = null
        var requestMethod: io.ktor.http.HttpMethod? = null
        val engine = MockEngine { request ->
            requestPath = request.url.encodedPath
            requestMethod = request.method
            respond("""{}""", status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val api = UploadsApi(client)
        api.complete("up-42", "videos/test.mp4", listOf(CompletedPart(1, "etag-a")))
        assertEquals("/uploads/complete", requestPath)
        assertEquals(io.ktor.http.HttpMethod.Post, requestMethod)
    }

    @Test
    fun presign_returnsPresignResponse() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            respond(
                """{"url":"https://r2.example.com/presigned-upload","key":"videos/small.mp4"}""",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val api = UploadsApi(client)
        val response = api.presign("small.mp4")
        assertEquals("https://r2.example.com/presigned-upload", response.url)
        assertEquals("videos/small.mp4", response.key)
    }

    @Test
    fun presign_sendsQueryParameters() = kotlinx.coroutines.test.runTest {
        var capturedUrl: String? = null
        val engine = MockEngine { request ->
            capturedUrl = request.url.toString()
            respond(
                """{"url":"https://r2.example.com/u","key":"k"}""",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val api = UploadsApi(client)
        api.presign("photo.jpg", "image/jpeg")
        val url = capturedUrl!!
        assert(url.contains("file_name=photo.jpg"))
        assert(url.contains("content_type=image%2Fjpeg"))
    }
}
