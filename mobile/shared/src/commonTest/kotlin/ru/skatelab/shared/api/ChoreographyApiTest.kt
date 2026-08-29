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
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import ru.skatelab.shared.models.GenerateRequest
import ru.skatelab.shared.models.LayoutElement
import ru.skatelab.shared.models.MusicUploadMetadata
import ru.skatelab.shared.models.RinkPosition
import ru.skatelab.shared.models.ValidateRequest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ChoreographyApiTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    private fun jsonHeaders() = headersOf(
        HttpHeaders.ContentType,
        ContentType.Application.Json.toString(),
    )

    @Test
    fun musicUploadMetadata_hasPlatformNeutralUploadPath() {
        val metadata = MusicUploadMetadata(
            fileName = "program.mp3",
            contentType = "audio/mpeg",
            sizeBytes = 1_024L,
        )

        assertEquals("program.mp3", metadata.fileName)
        assertEquals("audio/mpeg", metadata.contentType)
        assertEquals(1_024L, metadata.sizeBytes)
        assertEquals("choreography/music/upload", ChoreographyApi.musicUploadPath)
    }

    @Test
    fun getMusicAnalysis_parsesAnalysisPayload() = runTest {
        val engine = MockEngine { request ->
            assertEquals("/choreography/music/music-1/analysis", request.url.encodedPath)
            respond(
                """{
                    "id":"music-1",
                    "user_id":"user-1",
                    "filename":"program.mp3",
                    "audio_url":"/files/program.mp3",
                    "duration_sec":180.5,
                    "bpm":120.0,
                    "meter":"4/4",
                    "structure":[{"type":"verse","start":0.0,"end":30.0}],
                    "energy_curve":{"timestamps":[0.0],"values":[0.5]},
                    "downbeats":[0.0,0.5],
                    "peaks":[10.0],
                    "status":"completed",
                    "created_at":"2026-05-24T12:00:00Z",
                    "updated_at":"2026-05-24T12:01:00Z"
                }""",
                status = HttpStatusCode.OK,
                headers = jsonHeaders(),
            )
        }

        val response = ChoreographyApi(client(engine)).getMusicAnalysis("music-1")

        assertEquals("music-1", response.id)
        assertEquals(180.5, response.durationSec)
        assertEquals(120.0, response.bpm)
        assertEquals("verse", response.structure!![0].type)
        assertEquals(0.5, response.energyCurve!!.values[0])
        assertEquals("completed", response.status)
    }

    @Test
    fun getElementsRegistry_parsesRegistry() = runTest {
        val engine = MockEngine {
            respond(
                """{"elements":[{"code":"3Lz","name":"Triple Lutz","type":"jump","base_value":5.9,"rotations":3.0,"has_toe_pick":true,"entry_edge":"","exit_edge":"RBO","combo_eligible":true,"short_program_eligible":true}],"season":"2025_26"}""",
                status = HttpStatusCode.OK,
                headers = jsonHeaders(),
            )
        }

        val response = ChoreographyApi(client(engine)).getElementsRegistry()

        assertEquals("2025_26", response.season)
        assertEquals("3Lz", response.elements.single().code)
        assertEquals(5.9, response.elements.single().baseValue)
    }

    @Test
    fun validate_postsBackendRequest() = runTest {
        var path: String? = null
        val engine = MockEngine { request ->
            path = request.url.encodedPath
            respond(
                """{"is_valid":false,"errors":["Too many jumps"],"warnings":["Try a spin"],"total_tes":42.5}""",
                status = HttpStatusCode.OK,
                headers = jsonHeaders(),
            )
        }

        val response = ChoreographyApi(client(engine)).validate(
            ValidateRequest(
                discipline = "mens_singles",
                segment = "free_skate",
                elements = listOf(LayoutElement(code = "3A")),
            ),
        )

        assertEquals("/choreography/validate", path)
        assertEquals(false, response.isValid)
        assertEquals(42.5, response.totalTes)
        assertEquals(listOf("Too many jumps"), response.errors)
    }

    @Test
    fun generate_parsesLayouts() = runTest {
        val engine = MockEngine { request ->
            assertEquals("/choreography/generate", request.url.encodedPath)
            respond(
                """{"layouts":[{"elements":[{"code":"3A","goe":1.5,"timestamp":12.0,"position":{"x":10.0,"y":5.0},"is_back_half":true,"is_jump_pass":true,"jump_pass_index":0}],"total_tes":15.5,"back_half_indices":[0]}]}""",
                status = HttpStatusCode.OK,
                headers = jsonHeaders(),
            )
        }

        val response = ChoreographyApi(client(engine)).generate(
            GenerateRequest(
                musicId = "music-1",
                discipline = "mens_singles",
                segment = "free_skate",
                inventory = buildJsonObject { put("3A", JsonPrimitive(1)) },
            ),
        )

        assertEquals(1, response.layouts.size)
        assertEquals("3A", response.layouts[0].elements[0].code)
        assertEquals(10.0, response.layouts[0].elements[0].position!!.x)
        assertEquals(true, response.layouts[0].elements[0].isBackHalf)
    }

    @Test
    fun renderRink_returnsSvg() = runTest {
        val engine = MockEngine { request ->
            assertEquals("/choreography/render-rink", request.url.encodedPath)
            respond(
                """{"svg":"<svg>rink</svg>"}""",
                status = HttpStatusCode.OK,
                headers = jsonHeaders(),
            )
        }

        val response = ChoreographyApi(client(engine)).renderRink(
            elements = listOf(
                LayoutElement(code = "3A", position = RinkPosition(10.0, 5.0)),
            ),
        )

        assertEquals("<svg>rink</svg>", response.svg)
        assertTrue(response.svg.isNotEmpty())
    }
}
