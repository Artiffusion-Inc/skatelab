package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class PoseData(
    val poses: List<List<List<Float>>>,
    val fps: Float,
)

@Serializable
data class PhasesData(
    val takeoff: Int? = null,
    val peak: Int? = null,
    val landing: Int? = null,
)

enum class Phase {
    APPROACH, FLIGHT, LANDING
}

fun phaseForFrame(phases: PhasesData?, frameIndex: Int): Phase {
    if (phases == null) return Phase.APPROACH
    val takeoff = phases.takeoff ?: return Phase.APPROACH
    val landing = phases.landing ?: return Phase.APPROACH
    return when {
        frameIndex < takeoff -> Phase.APPROACH
        frameIndex < landing -> Phase.FLIGHT
        else -> Phase.LANDING
    }
}

@Serializable
data class FrameMetrics(
    @SerialName("knee_angles_r") val kneeAnglesR: List<Float>? = null,
    @SerialName("knee_angles_l") val kneeAnglesL: List<Float>? = null,
    @SerialName("hip_angles_r") val hipAnglesR: List<Float>? = null,
    @SerialName("hip_angles_l") val hipAnglesL: List<Float>? = null,
    @SerialName("trunk_lean") val trunkLean: List<Float>? = null,
    @SerialName("com_height") val comHeight: List<Float>? = null,
)
