package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.request.*
import io.ktor.http.*
import ru.skatelab.shared.models.UploadInitResponse
import ru.skatelab.shared.models.UploadCompleteRequest
import ru.skatelab.shared.models.CompletedPart
import kotlinx.serialization.Serializable

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
            setBody(UploadCompleteRequest(uploadId, key, parts))
        }
    }

    /** Get a presigned PUT URL for small file direct upload. */
    suspend fun presign(fileName: String, contentType: String = "application/octet-stream"): PresignResponse =
        client.post("/uploads/presign") {
            parameter("file_name", fileName)
            parameter("content_type", contentType)
        }.body()
}

@Serializable
data class PresignResponse(val url: String, val key: String)
