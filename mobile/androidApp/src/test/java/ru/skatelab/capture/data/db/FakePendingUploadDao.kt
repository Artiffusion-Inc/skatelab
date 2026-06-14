package ru.skatelab.capture.data.db

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.capture.data.db.PendingUploadEntity

/**
 * In-memory fake of PendingUploadDao for JVM tests.
 * Implements all DAO methods against a mutable map.
 */
class FakePendingUploadDao : PendingUploadDao {

    private val entities = mutableMapOf<String, PendingUploadEntity>()
    private val allFlow = MutableStateFlow<List<PendingUploadEntity>>(emptyList())
    private val countFlow = MutableStateFlow(0)

    private fun updateFlows() {
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
            entities[id] = entity.copy(status = "UPLOADING")
            updateFlows()
            1
        } else {
            0
        }
    }

    override suspend fun getById(id: String): PendingUploadEntity? {
        return entities[id]
    }

    override suspend fun getByIdFlow(id: String): Flow<PendingUploadEntity?> {
        // Simplified: returns current value, not reactive
        return MutableStateFlow(entities[id])
    }

    override suspend fun insert(entity: PendingUploadEntity) {
        entities[entity.id] = entity
        updateFlows()
    }

    override suspend fun updateStatus(id: String, status: String, sessionId: String?) {
        val entity = entities[id] ?: return
        entities[id] = entity.copy(status = status, sessionId = sessionId ?: entity.sessionId)
        updateFlows()
    }

    override suspend fun incrementRetry(id: String) {
        val entity = entities[id] ?: return
        entities[id] = entity.copy(retryCount = entity.retryCount + 1)
    }

    override suspend fun getAll(): Flow<List<PendingUploadEntity>> {
        return allFlow
    }

    override suspend fun countPending(): Flow<Int> {
        return countFlow
    }

    override suspend fun resetForRetry(id: String) {
        val entity = entities[id] ?: return
        entities[id] = entity.copy(status = "READY", retryCount = 0)
        updateFlows()
    }

    override suspend fun delete(id: String) {
        entities.remove(id)
        updateFlows()
    }

    override suspend fun updateVideoKey(id: String, videoKey: String) {
        val entity = entities[id] ?: return
        entities[id] = entity.copy(videoKey = videoKey)
        updateFlows()
    }
}
