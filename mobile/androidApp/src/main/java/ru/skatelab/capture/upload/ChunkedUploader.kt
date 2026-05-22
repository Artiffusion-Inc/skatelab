package ru.skatelab.capture.upload

import io.ktor.client.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import java.io.File
import java.io.RandomAccessFile
import java.util.concurrent.ConcurrentLinkedQueue
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import ru.skatelab.shared.api.UploadsApi
import ru.skatelab.shared.models.CompletedPart
import ru.skatelab.shared.models.UploadInitResponse

/**
 * Chunked multipart uploader ported from web's ChunkedUploader.
 *
 * Flow:
 * 1. POST /uploads/init — get presigned part URLs from R2
 * 2. PUT each chunk to its presigned URL (concurrency = 3)
 * 3. POST /uploads/complete — finalize multipart upload on R2
 *
 * Returns the R2 object key on success.
 */
class ChunkedUploader(
    private val uploadsApi: UploadsApi,
    private val httpClient: HttpClient,
) {
    companion object {
        private const val TAG = "ChunkedUploader"
        private const val CONCURRENCY = 3
    }

    /**
     * Upload a file via chunked multipart upload.
     * @param file the local file to upload
     * @param fileName override for the remote filename (defaults to file.name)
     * @param onProgress callback with (bytesUploaded, totalBytes)
     * @return the R2 object key
     */
    suspend fun upload(
        file: File,
        fileName: String = file.name,
        contentType: String = "video/mp4",
        onProgress: ((uploaded: Long, total: Long) -> Unit)? = null,
    ): String =
        withContext(Dispatchers.IO) {
            val totalSize = file.length().toInt()

            // Step 1: init multipart upload
            val init: UploadInitResponse = uploadsApi.init(fileName, contentType, totalSize)
            val chunkSize = init.chunkSize

            // Step 2: upload parts with bounded concurrency
            val semaphore = Semaphore(CONCURRENCY)
            val results = ConcurrentLinkedQueue<CompletedPart>()
            var uploaded = 0L

            coroutineScope {
                for (part in init.parts) {
                    launch {
                        semaphore.withPermit {
                            val start = (part.partNumber - 1) * chunkSize
                            val end = minOf(start + chunkSize, totalSize)
                            val chunkBytes = readFileChunk(file, start, end)

                            val etag = uploadPart(part.url, chunkBytes)
                            results.add(CompletedPart(part.partNumber, etag))

                            synchronized(this@withContext) {
                                uploaded += (end - start)
                                onProgress?.invoke(uploaded, totalSize.toLong())
                            }
                        }
                    }
                }
            }

            // Sort by part number to ensure correct order for completion
            val sortedParts = results.sortedBy { it.partNumber }

            // Step 3: complete multipart upload
            uploadsApi.complete(init.uploadId, init.key, sortedParts)

            init.key
        }

    private fun readFileChunk(
        file: File,
        start: Int,
        end: Int,
    ): ByteArray {
        return RandomAccessFile(file, "r").use { raf ->
            raf.seek(start.toLong())
            val size = end - start
            val buffer = ByteArray(size)
            raf.readFully(buffer, 0, size)
            buffer
        }
    }

    private suspend fun uploadPart(
        presignedUrl: String,
        chunk: ByteArray,
    ): String {
        val response: HttpResponse =
            httpClient.put(presignedUrl) {
                contentType(ContentType.Application.OctetStream)
                setBody(chunk)
            }
        if (!response.status.isSuccess()) {
            throw UploadException("Part upload failed: ${response.status.value} ${response.status.description}")
        }
        // ETag header from R2/S3
        return response.headers["ETag"]?.removeSurrounding("\"") ?: ""
    }
}

class UploadException(message: String) : Exception(message)
