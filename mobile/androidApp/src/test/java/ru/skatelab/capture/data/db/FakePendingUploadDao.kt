package ru.skatelab.capture.data.db

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow

/**
 * In-memory fake of PendingUploadDao for JVM tests.
 * Implements all DAO methods against a mutable map.
 */
class FakePendingUploadDao : PendingUploadDao {
    private val entities = mutableMapOf<String, PendingUploadEntity>()
    private val entityFlows = mutableMapOf<String, MutableStateFlow<PendingUploadEntity?>>()
    private val allFlow = MutableStateFlow<List<PendingUploadEntity>>(emptyList())
    private val countFlow = MutableStateFlow(0)

    private fun updateEntity(entity: PendingUploadEntity) {
        entities[entity.id] = entity
        entityFlows.getOrPut(entity.id) { MutableStateFlow(null) }.value = entity
        allFlow.value = entities.values.toList()
        countFlow.value = entities.values.count { it.status == "READY" || it.status == "UPLOADING" || it.status == "PROCESSING" }
    }

    override suspend fun getPending(): List<PendingUploadEntity> {
        return entities.values.filter {
            it.status in listOf("READY", "UPLOADING", "PROCESSING")
        }
    }

    override suspend fun tryLockForUpload(id: String): Int {
        val entity = entities[id] ?: return 0
        return if (entity.status == "READY") {
            updateEntity(entity.copy(status = "UPLOADING"))
            1
        } else {
            0
        }
    }

    override suspend fun getById(id: String): PendingUploadEntity? {
        return entities[id]
    }

    override fun getByIdFlow(id: String): Flow<PendingUploadEntity?> {
        return entityFlows.getOrPut(id) { MutableStateFlow(entities[id]) }
    }

    override suspend fun insert(entity: PendingUploadEntity) {
        updateEntity(entity)
    }

    override suspend fun updateStatus(
        id: String,
        status: String,
        sessionId: String?,
    ) {
        val entity = entities[id] ?: return
        updateEntity(entity.copy(status = status, sessionId = sessionId ?: entity.sessionId))
    }

    override suspend fun updateProcessingState(
        id: String,
        sessionId: String,
        processTaskId: String,
    ) {
        val entity = entities[id] ?: return
        updateEntity(
            entity.copy(
                status = "PROCESSING",
                sessionId = sessionId,
                processTaskId = processTaskId,
            ),
        )
    }

    override suspend fun incrementRetry(id: String) {
        val entity = entities[id] ?: return
        updateEntity(entity.copy(retryCount = entity.retryCount + 1))
    }

    override fun getAll(): Flow<List<PendingUploadEntity>> {
        return allFlow
    }

    override fun countPending(): Flow<Int> {
        return countFlow
    }

    override suspend fun resetForRetry(id: String) {
        val entity = entities[id] ?: return
        updateEntity(entity.copy(status = "READY", retryCount = 0))
    }

    override suspend fun delete(id: String) {
        entities.remove(id)
        entityFlows[id]?.value = null
        allFlow.value = entities.values.toList()
        countFlow.value = entities.values.count { it.status == "READY" || it.status == "UPLOADING" || it.status == "PROCESSING" }
    }

    override suspend fun updateVideoKey(
        id: String,
        videoKey: String,
    ) {
        val entity = entities[id] ?: return
        updateEntity(entity.copy(videoKey = videoKey))
    }
}
