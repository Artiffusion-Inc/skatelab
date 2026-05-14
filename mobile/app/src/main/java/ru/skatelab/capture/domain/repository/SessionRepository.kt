package ru.skatelab.capture.domain.repository

import kotlinx.coroutines.flow.StateFlow
import ru.skatelab.capture.domain.model.CaptureSession

interface SessionRepository {
    val sessions: StateFlow<List<CaptureSession>>
    suspend fun saveSession(session: CaptureSession): Result<Unit>
    suspend fun getSessions(): List<CaptureSession>
    suspend fun getSession(id: String): CaptureSession?
    suspend fun deleteSession(id: String): Result<Unit>
}
