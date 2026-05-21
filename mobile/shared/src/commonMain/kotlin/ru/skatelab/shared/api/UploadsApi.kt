package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.request.*
import io.ktor.http.*
import ru.skatelab.shared.models.UploadInitResponse
import ru.skatelab.shared.models.CompletedPart

class UploadsApi(private val client: HttpClient) {
    /** Initialize a multipart upload. Backend uses query parameters. */
    suspend fun init(fileName: String, contentType: String, totalSize: Int): UploadInitResponse =
        client.post("/uploads/init") {
            parameter("file_name", fileName)
            parameter("content_type", contentType)
            parameter("total_size", totalSize)
        }.body()

    /** Complete a multipart upload after all parts are uploaded to R2. */
    suspend fun complete(uploadId: String, key: String, parts: List<CompletedPart>) {
        client.post("/uploads/complete") {
            contentType(ContentType.Application.Json)
            setBody(mapOf(
                "upload_id" to uploadId,
                "key" to key,
                "parts" to parts.map { mapOf("part_number" to it.partNumber, "etag" to it.etag) },
            ))
        }
    }

    /** Get a presigned PUT URL for small file direct upload. */
    suspend fun presign(fileName: String, contentType: String = "application/octet-stream"): PresignResponse =
        client.post("/uploads/presign") {
            parameter("file_name", fileName)
            parameter("content_type", contentType)
        }.body()
}

@kotlinx.serialization.Serializable
data class PresignResponse(val url: String, val key: String)
