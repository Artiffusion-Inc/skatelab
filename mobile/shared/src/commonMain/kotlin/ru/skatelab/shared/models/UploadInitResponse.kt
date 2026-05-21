package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class UploadInitResponse(
    @SerialName("upload_id") val uploadId: String,
    val key: String,
    @SerialName("chunk_size") val chunkSize: Int,
    @SerialName("part_count") val partCount: Int,
    val parts: List<UploadPart>,
)

@Serializable
data class UploadPart(
    @SerialName("part_number") val partNumber: Int,
    val url: String,
)

@Serializable
data class UploadCompleteRequest(
    @SerialName("upload_id") val uploadId: String,
    val key: String,
    val parts: List<CompletedPart>,
)

@Serializable
data class CompletedPart(
    @SerialName("part_number") val partNumber: Int,
    val etag: String,
)
