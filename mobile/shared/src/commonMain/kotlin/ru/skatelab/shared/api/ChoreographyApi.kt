package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import ru.skatelab.shared.models.ElementRegistryResponse
import ru.skatelab.shared.models.GenerateRequest
import ru.skatelab.shared.models.GenerateResponse
import ru.skatelab.shared.models.LayoutElement
import ru.skatelab.shared.models.MUSIC_UPLOAD_PATH as MUSIC_UPLOAD_ENDPOINT
import ru.skatelab.shared.models.MusicAnalysisResponse
import ru.skatelab.shared.models.MusicUploadMetadata
import ru.skatelab.shared.models.RenderRinkRequest
import ru.skatelab.shared.models.RenderRinkResponse
import ru.skatelab.shared.models.ValidateRequest
import ru.skatelab.shared.models.ValidateResponse
import ru.skatelab.shared.utils.expectSuccess
import kotlinx.serialization.json.JsonElement

class ChoreographyApi(private val client: HttpClient) {
    companion object {
        /** Multipart upload route; the binary field is owned by a platform adapter. */
        const val MUSIC_UPLOAD_PATH: String = MUSIC_UPLOAD_ENDPOINT
        const val musicUploadPath: String = MUSIC_UPLOAD_PATH
    }

    /** Build the upload metadata passed between a platform file adapter and common code. */
    fun musicUploadMetadata(
        fileName: String,
        contentType: String,
        sizeBytes: Long,
    ): MusicUploadMetadata = MusicUploadMetadata(fileName, contentType, sizeBytes)

    /**
     * Read the current music analysis. Callers can poll this endpoint while status is pending
     * or analyzing; the backend does not provide a separate polling operation.
     */
    suspend fun getMusicAnalysis(musicId: String): MusicAnalysisResponse =
        client.get("choreography/music/$musicId/analysis").expectSuccess().body()

    suspend fun getAnalysis(musicId: String): MusicAnalysisResponse = getMusicAnalysis(musicId)

    suspend fun getElementsRegistry(): ElementRegistryResponse =
        client.get("choreography/elements/registry").expectSuccess().body()

    suspend fun getElementRegistry(): ElementRegistryResponse = getElementsRegistry()

    suspend fun validate(request: ValidateRequest): ValidateResponse =
        client.post("choreography/validate") {
            contentType(ContentType.Application.Json)
            setBody(request)
        }.expectSuccess().body()

    suspend fun validate(
        discipline: String,
        segment: String,
        elements: List<LayoutElement>,
    ): ValidateResponse = validate(ValidateRequest(discipline, segment, elements))

    suspend fun generate(request: GenerateRequest): GenerateResponse =
        client.post("choreography/generate") {
            contentType(ContentType.Application.Json)
            setBody(request)
        }.expectSuccess().body()

    suspend fun generate(
        musicId: String,
        discipline: String,
        segment: String,
        inventory: Map<String, JsonElement>,
    ): GenerateResponse = generate(GenerateRequest(musicId, discipline, segment, inventory))

    suspend fun renderRink(request: RenderRinkRequest): RenderRinkResponse =
        client.post("choreography/render-rink") {
            contentType(ContentType.Application.Json)
            setBody(request)
        }.expectSuccess().body()

    suspend fun renderRink(
        elements: List<LayoutElement>,
        width: Int = 1200,
        height: Int = 600,
        rinkWidth: Double = 60.0,
        rinkHeight: Double = 30.0,
    ): RenderRinkResponse = renderRink(
        RenderRinkRequest(elements, width, height, rinkWidth, rinkHeight),
    )
}
