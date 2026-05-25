package ru.skatelab.capture.data.db

import org.junit.Assert.assertEquals
import org.junit.Test

class CachedSessionEntityTest {
    @Test
    fun defaultValues() {
        val entity =
            CachedSessionEntity(
                id = "sess-1",
                elementType = "jump",
                status = "processing",
                createdAt = "2026-01-15T10:00:00Z",
            )
        assertEquals("sess-1", entity.id)
        assertEquals("jump", entity.elementType)
        assertEquals("processing", entity.status)
        assertEquals(null, entity.overallScore)
        assertEquals(null, entity.videoUrl)
        assertEquals("2026-01-15T10:00:00Z", entity.createdAt)
    }

    @Test
    fun allFieldsPopulated() {
        val entity =
            CachedSessionEntity(
                id = "sess-2",
                elementType = "spin",
                status = "completed",
                overallScore = 85.5f,
                videoUrl = "https://storage.example.com/video.mp4",
                createdAt = "2026-02-01T12:30:00Z",
            )
        assertEquals("sess-2", entity.id)
        assertEquals("spin", entity.elementType)
        assertEquals("completed", entity.status)
        assertEquals(85.5f, entity.overallScore!!, 0.01f)
        assertEquals("https://storage.example.com/video.mp4", entity.videoUrl)
    }

    @Test
    fun copyWithUpdatedScore() {
        val entity =
            CachedSessionEntity(
                id = "sess-1",
                elementType = "jump",
                status = "completed",
                createdAt = "2026-01-15T10:00:00Z",
            )
        val updated = entity.copy(overallScore = 92.3f, videoUrl = "https://cdn.example.com/v.mp4")
        assertEquals(92.3f, updated.overallScore!!, 0.01f)
        assertEquals("https://cdn.example.com/v.mp4", updated.videoUrl)
        assertEquals(null, entity.overallScore)
    }

    @Test
    fun dataClassEquality() {
        val e1 =
            CachedSessionEntity(
                id = "1",
                elementType = "jump",
                status = "ready",
                createdAt = "2026-01-01T00:00:00Z",
            )
        val e2 =
            CachedSessionEntity(
                id = "1",
                elementType = "jump",
                status = "ready",
                createdAt = "2026-01-01T00:00:00Z",
            )
        assertEquals(e1, e2)
    }
}
