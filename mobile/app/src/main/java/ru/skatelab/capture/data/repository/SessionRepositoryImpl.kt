package ru.skatelab.capture.data.repository

import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.repository.SessionRepository
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class SessionRepositoryImpl @Inject constructor() : SessionRepository {

    private val sessions = mutableListOf<CaptureSession>()

    override suspend fun saveSession(session: CaptureSession): Result<Unit> = runCatching {
        val existing = sessions.indexOfFirst { it.id == session.id }
        if (existing >= 0) {
            sessions[existing] = session
        } else {
            sessions.add(session)
        }
    }

    override suspend fun getSessions(): List<CaptureSession> = sessions.toList()

    override suspend fun getSession(id: String): CaptureSession? =
        sessions.find { it.id == id }

    override suspend fun deleteSession(id: String): Result<Unit> = runCatching {
        sessions.removeAll { it.id == id }
    }
}
