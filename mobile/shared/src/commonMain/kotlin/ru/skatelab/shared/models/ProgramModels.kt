package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class ProgramLayout(
    val elements: List<LayoutElement> = emptyList(),
    @SerialName("total_tes") val totalTes: Double? = null,
    @SerialName("back_half_indices") val backHalfIndices: List<Int> = emptyList(),
)

typealias ProgramLayoutElement = LayoutElement

@Serializable
data class ChoreographyProgramResponse(
    val id: String,
    @SerialName("user_id") val userId: String,
    @SerialName("workspace_id") val workspaceId: String? = null,
    @SerialName("music_analysis_id") val musicAnalysisId: String? = null,
    val title: String? = null,
    val discipline: String,
    val segment: String,
    val season: String,
    val layout: ProgramLayout? = null,
    @SerialName("total_tes") val totalTes: Double? = null,
    @SerialName("estimated_goe") val estimatedGoe: Double? = null,
    @SerialName("estimated_pcs") val estimatedPcs: Double? = null,
    @SerialName("estimated_total") val estimatedTotal: Double? = null,
    @SerialName("is_valid") val isValid: Boolean? = null,
    @SerialName("validation_errors") val validationErrors: List<String>? = null,
    @SerialName("validation_warnings") val validationWarnings: List<String>? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
)

typealias ProgramResponse = ChoreographyProgramResponse

@Serializable
data class ProgramListResponse(
    val programs: List<ChoreographyProgramResponse> = emptyList(),
    val total: Int = 0,
    val page: Int = 1,
    @SerialName("page_size") val pageSize: Int = 20,
    val pages: Int = 1,
)

@Serializable
data class SaveProgramRequest(
    @SerialName("music_analysis_id") val musicAnalysisId: String? = null,
    val discipline: String? = null,
    val segment: String? = null,
    val title: String? = null,
    val layout: ProgramLayout? = null,
    @SerialName("total_tes") val totalTes: Double? = null,
    @SerialName("estimated_goe") val estimatedGoe: Double? = null,
    @SerialName("estimated_pcs") val estimatedPcs: Double? = null,
    @SerialName("estimated_total") val estimatedTotal: Double? = null,
    @SerialName("is_valid") val isValid: Boolean? = null,
    @SerialName("validation_errors") val validationErrors: List<String>? = null,
    @SerialName("validation_warnings") val validationWarnings: List<String>? = null,
)

typealias ChoreographyProgramRequest = SaveProgramRequest

@Serializable
data class ExportRequest(
    val format: String,
)

enum class ExportFormat(val wireValue: String) {
    PDF("pdf"),
    SVG("svg"),
    JSON("json");

    companion object {
        fun fromWire(value: String): ExportFormat = entries.firstOrNull {
            it.wireValue == value.lowercase()
        } ?: error("Unsupported program export format: $value")
    }
}

@Serializable
data class ProgramExportData(
    val id: String,
    val title: String? = null,
    val discipline: String = "",
    val segment: String = "",
    val season: String = "",
    @SerialName("music_analysis_id") val musicAnalysisId: String? = null,
    val layout: ProgramLayout? = null,
    @SerialName("total_tes") val totalTes: Double? = null,
    @SerialName("estimated_goe") val estimatedGoe: Double? = null,
    @SerialName("estimated_pcs") val estimatedPcs: Double? = null,
    @SerialName("estimated_total") val estimatedTotal: Double? = null,
    @SerialName("is_valid") val isValid: Boolean? = null,
    @SerialName("validation_errors") val validationErrors: List<String>? = null,
    @SerialName("validation_warnings") val validationWarnings: List<String>? = null,
)

@Serializable
internal data class ProgramSvgExportPayload(
    val format: String = "svg",
    val svg: String,
)

@Serializable
internal data class ProgramJsonExportPayload(
    val format: String = "json",
    val data: ProgramExportData,
)

sealed interface ProgramExportResponse {
    val format: ExportFormat

    data class Pdf(
        val bytes: ByteArray,
        val fileName: String? = null,
        val contentType: String = "application/pdf",
    ) : ProgramExportResponse {
        override val format: ExportFormat = ExportFormat.PDF
    }

    data class Svg(
        val svg: String,
    ) : ProgramExportResponse {
        override val format: ExportFormat = ExportFormat.SVG
    }

    data class Json(
        val data: ProgramExportData,
    ) : ProgramExportResponse {
        override val format: ExportFormat = ExportFormat.JSON
    }
}

typealias PdfExportResponse = ProgramExportResponse.Pdf
typealias SvgExportResponse = ProgramExportResponse.Svg
typealias JsonExportResponse = ProgramExportResponse.Json
