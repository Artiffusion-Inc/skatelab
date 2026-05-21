package ru.skatelab.capture.domain.model

data class ImuChartData(
    val timeSeconds: FloatArray,
    val accMagLeft: FloatArray,
    val angVelLeft: FloatArray,
    val rotLeft: FloatArray,
    val accMagRight: FloatArray,
    val angVelRight: FloatArray,
    val rotRight: FloatArray,
) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is ImuChartData) return false
        return timeSeconds.contentEquals(other.timeSeconds) &&
            accMagLeft.contentEquals(other.accMagLeft) &&
            angVelLeft.contentEquals(other.angVelLeft) &&
            rotLeft.contentEquals(other.rotLeft) &&
            accMagRight.contentEquals(other.accMagRight) &&
            angVelRight.contentEquals(other.angVelRight) &&
            rotRight.contentEquals(other.rotRight)
    }

    override fun hashCode(): Int {
        var result = timeSeconds.contentHashCode()
        result = 31 * result + accMagLeft.contentHashCode()
        result = 31 * result + angVelLeft.contentHashCode()
        result = 31 * result + rotLeft.contentHashCode()
        result = 31 * result + accMagRight.contentHashCode()
        result = 31 * result + angVelRight.contentHashCode()
        result = 31 * result + rotRight.contentHashCode()
        return result
    }
}
