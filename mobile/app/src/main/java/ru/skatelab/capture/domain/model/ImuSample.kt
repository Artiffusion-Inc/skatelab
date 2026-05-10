package ru.skatelab.capture.domain.model

data class ImuSample(
    val timestampNs: Long,
    val accX: Float, val accY: Float, val accZ: Float,
    val gyroX: Float, val gyroY: Float, val gyroZ: Float,
    val quatW: Float, val quatX: Float, val quatY: Float, val quatZ: Float,
)
