package ru.skatelab.capture.upload

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import ru.skatelab.capture.data.db.PendingUploadEntity

class UploadWorkerTest {
    @Test
    fun inputData_containsUploadId() {
        val data = UploadWorker.inputData("test-123")
        assertEquals("test-123", data.getString(UploadWorker.KEY_UPLOAD_ID))
    }

    @Test
    fun pendingUploadEntity_hasCorrectDefaults() {
        val entity =
            PendingUploadEntity(
                id = "up-1",
                videoPath = "/tmp/video.mp4",
            )
        assertEquals("up-1", entity.id)
        assertEquals("/tmp/video.mp4", entity.videoPath)
        assertEquals(null, entity.imuLeftPath)
        assertEquals(null, entity.imuRightPath)
        assertEquals("READY", entity.status)
        assertEquals(0, entity.retryCount)
    }

    @Test
    fun pendingUploadEntity_withImuPaths() {
        val entity =
            PendingUploadEntity(
                id = "up-2",
                videoPath = "/tmp/video.mp4",
                imuLeftPath = "/tmp/left.binpb",
                imuRightPath = "/tmp/right.binpb",
                manifestPath = "/tmp/manifest.json",
            )
        assertEquals("/tmp/left.binpb", entity.imuLeftPath)
        assertEquals("/tmp/right.binpb", entity.imuRightPath)
        assertEquals("/tmp/manifest.json", entity.manifestPath)
    }

    @Test
    fun uploadException_messagePreserved() {
        val ex = UploadException("Presigned upload failed: 403")
        assertEquals("Presigned upload failed: 403", ex.message)
    }

    @Test
    fun pendingUploadEntity_statusTransitions() {
        val entity =
            PendingUploadEntity(
                id = "up-3",
                videoPath = "/tmp/v.mp4",
                status = "UPLOADING",
                retryCount = 1,
            )
        assertEquals("UPLOADING", entity.status)
        assertEquals(1, entity.retryCount)
    }

    @Test
    fun uploadException_isException_subclass() {
        val ex = UploadException("test")
        assertTrue(ex is Exception)
    }

    @Test
    fun pendingUploadEntity_elementType_nullFallsBackToAxel() {
        val entity = PendingUploadEntity(id = "1", videoPath = "/path.mp4")
        val resolved = entity.elementType ?: "axel"
        assertEquals("axel", resolved)
    }

    @Test
    fun pendingUploadEntity_elementType_setValueUsed() {
        val entity = PendingUploadEntity(id = "1", videoPath = "/path.mp4", elementType = "lutz")
        val resolved = entity.elementType ?: "axel"
        assertEquals("lutz", resolved)
    }

    @Test
    fun pendingUploadEntity_status_networkError() {
        val entity = PendingUploadEntity(id = "up-net", videoPath = "/tmp/v.mp4", status = "NETWORK_ERROR")
        assertEquals("NETWORK_ERROR", entity.status)
    }
}
