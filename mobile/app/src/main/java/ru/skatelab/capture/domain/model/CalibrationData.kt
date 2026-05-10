package ru.skatelab.capture.domain.model

data class CalibrationData(
    val quatRef: FloatArray,
    val calibratedAt: Long,
) {
    init { require(quatRef.size == 4) { "Quaternion must have 4 components" } }
    companion object { val IDENTITY = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 0L) }
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is CalibrationData) return false
        return quatRef.contentEquals(other.quatRef) && calibratedAt == other.calibratedAt
    }
    override fun hashCode(): Int = 31 * quatRef.contentHashCode() + calibratedAt.hashCode()
}
