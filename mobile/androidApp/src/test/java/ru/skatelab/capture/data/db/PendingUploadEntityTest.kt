package ru.skatelab.capture.data.db

import org.junit.Assert.assertEquals
import org.junit.Test

class PendingUploadEntityTest {
    @Test
    fun defaultValues() {
        val entity =
            PendingUploadEntity(
                id = "test-id",
                videoPath = "/path/to/video.mp4",
            )
        assertEquals("test-id", entity.id)
        assertEquals("/path/to/video.mp4", entity.videoPath)
        assertEquals(null, entity.imuLeftPath)
        assertEquals(null, entity.imuRightPath)
        assertEquals(null, entity.manifestPath)
        assertEquals(null, entity.elementType)
        assertEquals("READY", entity.status)
        assertEquals(null, entity.uploadId)
        assertEquals(null, entity.videoKey)
        assertEquals(null, entity.sessionId)
        assertEquals(0, entity.retryCount)
    }

    @Test
    fun allFieldsPopulated() {
        val entity =
            PendingUploadEntity(
                id = "upload-123",
                videoPath = "/tmp/video.mp4",
                imuLeftPath = "/tmp/imu_left.protobuf",
                imuRightPath = "/tmp/imu_right.protobuf",
                manifestPath = "/tmp/manifest.json",
                status = "UPLOADING",
                uploadId = "up-456",
                videoKey = "sessions/123/video.mp4",
                sessionId = "sess-789",
                retryCount = 2,
            )
        assertEquals("upload-123", entity.id)
        assertEquals("/tmp/video.mp4", entity.videoPath)
        assertEquals("/tmp/imu_left.protobuf", entity.imuLeftPath)
        assertEquals("/tmp/imu_right.protobuf", entity.imuRightPath)
        assertEquals("/tmp/manifest.json", entity.manifestPath)
        assertEquals(null, entity.elementType)
        assertEquals("UPLOADING", entity.status)
        assertEquals("up-456", entity.uploadId)
        assertEquals("sessions/123/video.mp4", entity.videoKey)
        assertEquals("sess-789", entity.sessionId)
        assertEquals(2, entity.retryCount)
    }

    @Test
    fun copyWithUpdatedStatus() {
        val entity =
            PendingUploadEntity(
                id = "test-id",
                videoPath = "/path/to/video.mp4",
            )
        val updated = entity.copy(status = "COMPLETED", sessionId = "sess-1")
        assertEquals("COMPLETED", updated.status)
        assertEquals("sess-1", updated.sessionId)
        assertEquals("READY", entity.status)
    }

    @Test
    fun dataClassEquality() {
        val ts = System.currentTimeMillis()
        val e1 = PendingUploadEntity(id = "1", videoPath = "/v.mp4", createdAt = ts)
        val e2 = PendingUploadEntity(id = "1", videoPath = "/v.mp4", createdAt = ts)
        assertEquals(e1, e2)
    }

    @Test
    fun elementType_nullByDefault() {
        val entity = PendingUploadEntity(id = "1", videoPath = "/path.mp4")
        assertEquals(null, entity.elementType)
    }

    @Test
    fun elementType_preservedWhenSet() {
        val entity = PendingUploadEntity(id = "1", videoPath = "/path.mp4", elementType = "flip")
        assertEquals("flip", entity.elementType)
    }
}
