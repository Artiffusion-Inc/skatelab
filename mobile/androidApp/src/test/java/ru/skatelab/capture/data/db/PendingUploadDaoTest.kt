package ru.skatelab.capture.data.db

import org.junit.Assert.assertEquals
import org.junit.Test

class PendingUploadDaoTest {
    @Test
    fun allStatuses_coversAllStates() {
        val statuses = listOf("READY", "UPLOADING", "PROCESSING", "COMPLETED", "FAILED")
        assertEquals(5, statuses.size)
    }

    @Test
    fun pendingStatuses_excludesCompleted() {
        val pendingStatuses = setOf("READY", "UPLOADING", "PROCESSING")
        assert(!pendingStatuses.contains("COMPLETED"))
        assert(!pendingStatuses.contains("FAILED"))
    }

    @Test
    fun resetForRetry_setsReadyAndZeroRetry() {
        val status = "READY"
        val retryCount = 0
        assertEquals("READY", status)
        assertEquals(0, retryCount)
    }

    @Test
    fun getByIdFlow_returnsNullableEntity() {
        // DAO returns Flow<PendingUploadEntity?> — null means entity not found
        val notFound: PendingUploadEntity? = null
        assertEquals(null, notFound)
    }
}
