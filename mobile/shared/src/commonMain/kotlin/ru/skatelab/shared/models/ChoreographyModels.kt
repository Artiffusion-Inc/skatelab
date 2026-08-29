package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/** Metadata a platform uploader can provide without exposing File/URL types to commonMain. */
@Serializable
data class MusicUploadMetadata(
    @SerialName("filename") val fileName: String,
    @SerialName("content_type") val contentType: String,
    @SerialName("size_bytes") val sizeBytes: Long,
)

@Serializable
data class UploadMusicResponse(
    @SerialName("music_id") val musicId: String,
    val filename: String,
)

@Serializable
data class MusicStructureSegment(
    val type: String,
    val start: Double,
    val end: Double,
)

typealias MusicSegment = MusicStructureSegment

@Serializable
data class EnergyCurve(
    val timestamps: List<Double> = emptyList(),
    val values: List<Double> = emptyList(),
)

typealias EnergyCurveData = EnergyCurve

@Serializable
data class MusicAnalysisResponse(
    val id: String,
    @SerialName("user_id") val userId: String,
    @SerialName("workspace_id") val workspaceId: String? = null,
    val filename: String,
    @SerialName("audio_url") val audioUrl: String,
    @SerialName("duration_sec") val durationSec: Double,
    val bpm: Double? = null,
    val meter: String? = null,
    val structure: List<MusicStructureSegment>? = null,
    @SerialName("energy_curve") val energyCurve: EnergyCurve? = null,
    val downbeats: List<Double>? = null,
    val peaks: List<Double>? = null,
    val status: String,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
)

typealias MusicAnalysis = MusicAnalysisResponse

@Serializable
data class GenerateRequest(
    @SerialName("music_id") val musicId: String,
    val discipline: String,
    val segment: String,
    val inventory: Map<String, JsonElement>,
)

@Serializable
data class RinkPosition(
    val x: Double,
    val y: Double,
)

typealias LayoutPosition = RinkPosition

@Serializable
data class LayoutElement(
    val code: String,
    val goe: Double = 0.0,
    val timestamp: Double = 0.0,
    val position: RinkPosition? = null,
    @SerialName("is_back_half") val isBackHalf: Boolean = false,
    @SerialName("is_jump_pass") val isJumpPass: Boolean = false,
    @SerialName("jump_pass_index") val jumpPassIndex: Int? = null,
)

@Serializable
data class Layout(
    val elements: List<LayoutElement> = emptyList(),
    @SerialName("total_tes") val totalTes: Double = 0.0,
    @SerialName("back_half_indices") val backHalfIndices: List<Int> = emptyList(),
)

@Serializable
data class GenerateResponse(
    val layouts: List<Layout> = emptyList(),
)

@Serializable
data class ValidateRequest(
    val discipline: String,
    val segment: String,
    val elements: List<LayoutElement>,
)

@Serializable
data class ValidateResponse(
    @SerialName("is_valid") val isValid: Boolean,
    val errors: List<String> = emptyList(),
    val warnings: List<String> = emptyList(),
    @SerialName("total_tes") val totalTes: Double? = null,
)

@Serializable
data class RenderRinkRequest(
    val elements: List<LayoutElement>,
    val width: Int = 1200,
    val height: Int = 600,
    @SerialName("rink_width") val rinkWidth: Double = 60.0,
    @SerialName("rink_height") val rinkHeight: Double = 30.0,
)

@Serializable
data class RenderRinkResponse(
    val svg: String,
)

typealias RinkRenderResponse = RenderRinkResponse

@Serializable
data class ElementDefinition(
    val code: String,
    val name: String,
    val type: String,
    @SerialName("base_value") val baseValue: Double,
    val rotations: Double,
    @SerialName("has_toe_pick") val hasToePick: Boolean,
    @SerialName("entry_edge") val entryEdge: String,
    @SerialName("exit_edge") val exitEdge: String,
    @SerialName("combo_eligible") val comboEligible: Boolean,
    @SerialName("short_program_eligible") val shortProgramEligible: Boolean,
)

@Serializable
data class ElementRegistryResponse(
    val elements: List<ElementDefinition> = emptyList(),
    val season: String,
)

typealias ElementDefResponse = ElementDefinition

/** The upload route is multipart-only; binary transfer is deliberately left to a platform adapter. */
const val MUSIC_UPLOAD_PATH: String = "choreography/music/upload"
