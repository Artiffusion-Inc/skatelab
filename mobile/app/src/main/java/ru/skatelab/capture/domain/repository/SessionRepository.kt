package ru.skatelab.capture.domain.repository

import ru.skatelab.capture.domain.model.CaptureSession

interface SessionRepository {
    suspend fun saveSession(session: CaptureSession): Result<Unit>
    suspend fun getSessions(): List<CaptureSession>
    suspend fun getSession(id: String): CaptureSession?
    suspend fun deleteSession(id: String): Result<Unit>
}
