package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.parameter
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.contentType
import ru.skatelab.shared.models.ChoreographyProgramResponse
import ru.skatelab.shared.models.ExportFormat
import ru.skatelab.shared.models.ExportRequest
import ru.skatelab.shared.models.ProgramExportResponse
import ru.skatelab.shared.models.ProgramJsonExportPayload
import ru.skatelab.shared.models.ProgramListResponse
import ru.skatelab.shared.models.ProgramSvgExportPayload
import ru.skatelab.shared.models.SaveProgramRequest
import ru.skatelab.shared.utils.expectSuccess

class ProgramsApi(private val client: HttpClient) {
    suspend fun list(limit: Int = 20, offset: Int = 0): ProgramListResponse =
        client.get("choreography/programs") {
            parameter("limit", limit)
            parameter("offset", offset)
        }.expectSuccess().body()

    suspend fun get(programId: String): ChoreographyProgramResponse =
        client.get("choreography/programs/$programId").expectSuccess().body()

    suspend fun create(request: SaveProgramRequest): ChoreographyProgramResponse =
        client.post("choreography/programs") {
            contentType(ContentType.Application.Json)
            setBody(request)
        }.expectSuccess().body()

    suspend fun update(
        programId: String,
        request: SaveProgramRequest,
    ): ChoreographyProgramResponse =
        client.put("choreography/programs/$programId") {
            contentType(ContentType.Application.Json)
            setBody(request)
        }.expectSuccess().body()

    suspend fun delete(programId: String) {
        client.delete("choreography/programs/$programId").expectSuccess()
    }

    suspend fun export(
        programId: String,
        format: ExportFormat,
    ): ProgramExportResponse = export(programId, format.wireValue)

    suspend fun export(
        programId: String,
        format: String,
    ): ProgramExportResponse {
        val requestedFormat = ExportFormat.fromWire(format)
        val response = client.post("choreography/programs/$programId/export") {
            contentType(ContentType.Application.Json)
            setBody(ExportRequest(requestedFormat.wireValue))
        }.expectSuccess()

        return when (requestedFormat) {
            ExportFormat.PDF -> response.toPdfExport()
            ExportFormat.SVG -> response.toSvgExport()
            ExportFormat.JSON -> response.toJsonExport()
        }
    }

    private suspend fun HttpResponse.toPdfExport(): ProgramExportResponse.Pdf {
        val contentType = headers[HttpHeaders.ContentType] ?: ContentType.Application.Pdf.toString()
        return ProgramExportResponse.Pdf(
            bytes = body(),
            fileName = parseFileName(headers[HttpHeaders.ContentDisposition]),
            contentType = contentType,
        )
    }

    private suspend fun HttpResponse.toSvgExport(): ProgramExportResponse.Svg {
        val payload: ProgramSvgExportPayload = body()
        return ProgramExportResponse.Svg(payload.svg)
    }

    private suspend fun HttpResponse.toJsonExport(): ProgramExportResponse.Json {
        val payload: ProgramJsonExportPayload = body()
        return ProgramExportResponse.Json(payload.data)
    }

    private fun parseFileName(contentDisposition: String?): String? {
        if (contentDisposition == null) return null
        val quoted = contentDisposition.substringAfter("filename=\"", "")
        if (quoted.isNotEmpty()) return quoted.substringBefore('"')
        return contentDisposition.substringAfter("filename=", "")
            .substringBefore(';')
            .trim()
            .ifEmpty { null }
    }
}
