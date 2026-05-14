package ru.skatelab.capture.domain.model

data class SensorInfo(
    val deviceId: String,
    val firmwareVersion: String,
    val batteryPercent: Int,
    val batteryMv: Int,
)