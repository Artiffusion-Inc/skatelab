package ru.skatelab.shared.state

interface AuthRecoveryApi {
    suspend fun forgotPassword(email: String)
}
