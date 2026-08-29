package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondOk
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import ru.skatelab.shared.models.ExportFormat
import ru.skatelab.shared.models.LayoutElement
import ru.skatelab.shared.models.ProgramExportResponse
import ru.skatelab.shared.models.ProgramLayout
import ru.skatelab.shared.models.SaveProgramRequest
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertIs

class ProgramsApiTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    private fun jsonHeaders() = headersOf(
        HttpHeaders.ContentType,
        ContentType.Application.Json.toString(),
    )

    private val programJson = """{
        "id":"program-1",
        "user_id":"user-1",
        "workspace_id":null,
        "music_analysis_id":"music-1",
        "title":"Free skate",
        "discipline":"mens_singles",
        "segment":"free_skate",
        "season":"2025_26",
        "layout":{"elements":[{"code":"3A","goe":1.0,"timestamp":12.0}],"total_tes":8.8,"back_half_indices":[0]},
        "total_tes":50.0,
        "estimated_goe":5.0,
        "estimated_pcs":80.0,
        "estimated_total":135.0,
        "is_valid":true,
        "validation_errors":[],
        "validation_warnings":[],
        "created_at":"2026-05-24T12:00:00Z",
        "updated_at":"2026-05-24T12:01:00Z"
    }"""

    @Test
    fun list_passesPaginationAndParsesPrograms() = runTest {
        var method: HttpMethod? = null
        var path: String? = null
        var query: String? = null
        val engine = MockEngine { request ->
            method = request.method
            path = request.url.encodedPath
            query = request.url.encodedQuery
            respond(
                """{"programs":[$programJson],"total":1,"page":2,"page_size":10,"pages":3}""",
                status = HttpStatusCode.OK,
                headers = jsonHeaders(),
            )
        }

        val response = ProgramsApi(client(engine)).list(limit = 10, offset = 10)

        assertEquals(HttpMethod.Get, method)
        assertEquals("/choreography/programs", path)
        assertEquals(true, query!!.contains("limit=10"))
        assertEquals(true, query!!.contains("offset=10"))
        assertEquals(1, response.programs.size)
        assertEquals("program-1", response.programs[0].id)
        assertEquals("3A", response.programs[0].layout!!.elements[0].code)
        assertEquals(8.8, response.programs[0].layout!!.totalTes)
        assertEquals(listOf(0), response.programs[0].layout!!.backHalfIndices)
    }

    @Test
    fun get_returnsProgram() = runTest {
        val engine = MockEngine { request ->
            assertEquals("/choreography/programs/program-1", request.url.encodedPath)
            respond(programJson, status = HttpStatusCode.OK, headers = jsonHeaders())
        }

        val response = ProgramsApi(client(engine)).get("program-1")

        assertEquals("program-1", response.id)
        assertEquals("Free skate", response.title)
    }

    @Test
    fun createAndUpdate_useProgramPayloads() = runTest {
        val methods = mutableListOf<HttpMethod>()
        val paths = mutableListOf<String>()
        val engine = MockEngine { request ->
            methods += request.method
            paths += request.url.encodedPath
            respond(programJson, status = HttpStatusCode.OK, headers = jsonHeaders())
        }
        val api = ProgramsApi(client(engine))
        val body = SaveProgramRequest(
            musicAnalysisId = "music-1",
            title = "Free skate",
            discipline = "mens_singles",
            segment = "free_skate",
            layout = ProgramLayout(elements = listOf(LayoutElement(code = "3A"))),
        )

        val created = api.create(body)
        val updated = api.update("program-1", body)

        assertEquals("program-1", created.id)
        assertEquals("program-1", updated.id)
        assertEquals(listOf(HttpMethod.Post, HttpMethod.Put), methods)
        assertEquals(
            listOf("/choreography/programs", "/choreography/programs/program-1"),
            paths,
        )
    }

    @Test
    fun delete_sendsDeleteRequest() = runTest {
        var method: HttpMethod? = null
        var path: String? = null
        val engine = MockEngine { request ->
            method = request.method
            path = request.url.encodedPath
            respondOk()
        }

        ProgramsApi(client(engine)).delete("program-1")

        assertEquals(HttpMethod.Delete, method)
        assertEquals("/choreography/programs/program-1", path)
    }

    @Test
    fun export_parsesPdfBytes() = runTest {
        val bytes = byteArrayOf(0x25, 0x50, 0x44, 0x46)
        val engine = MockEngine {
            respond(
                bytes,
                status = HttpStatusCode.OK,
                headers = headersOf(
                    HttpHeaders.ContentType to listOf(ContentType.Application.Pdf.toString()),
                    HttpHeaders.ContentDisposition to listOf("attachment; filename=\"program-program-1.pdf\""),
                ),
            )
        }

        val response = ProgramsApi(client(engine)).export("program-1", ExportFormat.PDF)
        val pdf = assertIs<ProgramExportResponse.Pdf>(response)

        assertContentEquals(bytes, pdf.bytes)
        assertEquals("program-program-1.pdf", pdf.fileName)
        assertEquals(ExportFormat.PDF, pdf.format)
    }

    @Test
    fun export_parsesSvgResponse() = runTest {
        val engine = MockEngine {
            respond(
                """{"format":"svg","svg":"<svg>rink</svg>"}""",
                status = HttpStatusCode.OK,
                headers = jsonHeaders(),
            )
        }

        val response = ProgramsApi(client(engine)).export("program-1", ExportFormat.SVG)
        val svg = assertIs<ProgramExportResponse.Svg>(response)

        assertEquals("<svg>rink</svg>", svg.svg)
        assertEquals(ExportFormat.SVG, svg.format)
    }

    @Test
    fun export_parsesJsonResponse() = runTest {
        val engine = MockEngine {
            respond(
                """{"format":"json","data":{"id":"program-1","title":"Free skate","layout":{"elements":[]}}}""",
                status = HttpStatusCode.OK,
                headers = jsonHeaders(),
            )
        }

        val response = ProgramsApi(client(engine)).export("program-1", ExportFormat.JSON)
        val export = assertIs<ProgramExportResponse.Json>(response)

        assertEquals("program-1", export.data.id)
        assertEquals("Free skate", export.data.title)
        assertEquals(0, export.data.layout!!.elements.size)
    }
}
