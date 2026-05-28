package ru.skatelab.capture.ui.skeleton

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.shared.models.PoseData
import ru.skatelab.shared.models.PhasesData
import ru.skatelab.shared.models.Phase
import ru.skatelab.shared.models.phaseForFrame
import ru.skatelab.shared.utils.interpolatePose

/**
 * A single keypoint in normalized [0, 1] coordinates.
 * [confidence] is in [0, 1]; points below [confidenceThreshold] are skipped.
 */
data class Keypoint(
    val x: Float,
    val y: Float,
    val confidence: Float = 1f,
)

/**
 * H3.6M 17-keypoint skeleton connections (start index, end index).
 * Matches the web skeleton-canvas.tsx definition exactly.
 */
val H36M_CONNECTIONS =
    listOf(
        // Right leg: hip_center->r_hip->r_knee->r_foot
        0 to 1,
        1 to 2,
        2 to 3,
        // Left leg: hip_center->l_hip->l_knee->l_foot
        0 to 4,
        4 to 5,
        5 to 6,
        // Spine + head: hip_center->spine->thorax->neck->head_top
        0 to 7,
        7 to 8,
        8 to 9,
        9 to 10,
        // Left arm: neck->l_shoulder->l_elbow->l_wrist
        9 to 11,
        11 to 12,
        12 to 13,
        // Right arm: neck->r_shoulder->r_elbow->r_wrist
        9 to 14,
        14 to 15,
        15 to 16,
    )

/**
 * Joint colors matching web skeleton-canvas.tsx JOINT_COLORS.
 * Indexed by H3.6M keypoint index (0..16).
 */
val H36M_JOINT_COLORS =
    listOf(
        // 0: hip_center, 1-3: right leg (green), 4-6: left leg (blue)
        Color.Red,
        Color(0f, 1f, 0f),
        Color(0f, 1f, 0f),
        Color(0f, 1f, 0f),
        Color(0f, 0f, 1f),
        Color(0f, 0f, 1f),
        Color(0f, 0f, 1f),
        // 7-8: spine/thorax (yellow), 9-10: neck/head (magenta)
        Color.Yellow,
        Color.Yellow,
        Color.Magenta,
        Color.Magenta,
        // 11-13: left arm (cyan), 14-16: right arm (orange)
        Color.Cyan,
        Color.Cyan,
        Color.Cyan,
        Color(red = 1f, green = 0.647f, blue = 0f),
        Color(red = 1f, green = 0.647f, blue = 0f),
        Color(red = 1f, green = 0.647f, blue = 0f),
    )

/** Line color for skeleton bones. */
private val BONE_COLOR = Color.White.copy(alpha = 0.6f)

/** Minimum confidence to draw a joint or bone. */
private const val DEFAULT_CONFIDENCE_THRESHOLD = 0.3f

/** Joint circle radius in dp. */
private val JOINT_RADIUS_DP = 4.dp

/** Center-of-mass dot radius in dp. */
private val COM_RADIUS_DP = 6.dp

/** Bone line width in dp. */
private val BONE_WIDTH_DP = 2.dp

/** CoM outline width in dp. */
private val COM_OUTLINE_DP = 1.dp

/**
 * A Compose [Canvas] composable that draws an H3.6M skeleton overlay.
 *
 * Designed to sit on top of an ExoPlayer video via a [Box] with matching size.
 * Keypoints use normalized [0, 1] coordinates — the composable maps them
 * to pixel offsets based on its own measured width/height.
 *
 * @param keypoints 17 H3.6M keypoints for the current frame (null = not available).
 * @param modifier Standard modifier (fillMaxSize, matchParent, etc.).
 * @param confidenceThreshold Discard keypoints below this confidence.
 * @param showCenterOfMass Draw a weighted CoM dot at pelvis/spine/neck/head.
 */
@Composable
fun SkeletonOverlay(
    keypoints: List<Keypoint?>?,
    modifier: Modifier = Modifier,
    confidenceThreshold: Float = DEFAULT_CONFIDENCE_THRESHOLD,
    showCenterOfMass: Boolean = true,
) {
    val density = LocalDensity.current
    val context = LocalContext.current
    val jointRadiusPx = with(density) { JOINT_RADIUS_DP.toPx() }
    val comRadiusPx = with(density) { COM_RADIUS_DP.toPx() }
    val boneWidthPx = with(density) { BONE_WIDTH_DP.toPx() }
    val comOutlinePx = with(density) { COM_OUTLINE_DP.toPx() }

    Canvas(
        modifier =
            modifier.clearAndSetSemantics {
                contentDescription = context.getString(R.string.cd_skeleton_overlay)
                role = Role.Image
            },
    ) {
        if (keypoints == null) return@Canvas
        if (keypoints.size < 17) return@Canvas

        val w = size.width
        val h = size.height

        // ── Draw skeleton bones ──
        for ((start, end) in H36M_CONNECTIONS) {
            val kpStart = keypoints[start]
            val kpEnd = keypoints[end]
            if (kpStart == null || kpEnd == null) continue
            if (kpStart.confidence < confidenceThreshold) continue
            if (kpEnd.confidence < confidenceThreshold) continue

            drawLine(
                color = BONE_COLOR,
                start = Offset(kpStart.x * w, kpStart.y * h),
                end = Offset(kpEnd.x * w, kpEnd.y * h),
                strokeWidth = boneWidthPx,
            )
        }

        // ── Draw joint circles ──
        for (i in keypoints.indices) {
            val kp = keypoints[i] ?: continue
            if (kp.confidence < confidenceThreshold) continue
            val color = H36M_JOINT_COLORS.getOrElse(i) { Color.White }
            drawCircle(
                color = color,
                radius = jointRadiusPx,
                center = Offset(kp.x * w, kp.y * h),
            )
        }

        // ── Draw center of mass ──
        if (showCenterOfMass) {
            val pelvis = keypoints[0]
            val thorax = keypoints[8]
            val neck = keypoints[9]
            val head = keypoints[10]
            if (pelvis != null && thorax != null && neck != null && head != null) {
                val comX = (pelvis.x * 0.5f + thorax.x * 0.3f + neck.x * 0.15f + head.x * 0.05f) * w
                val comY = (pelvis.y * 0.5f + thorax.y * 0.3f + neck.y * 0.15f + head.y * 0.05f) * h
                drawCircle(
                    color = Color(red = 0xEF, green = 0x44, blue = 0x44),
                    radius = comRadiusPx,
                    center = Offset(comX, comY),
                )
                // White outline
                drawCircle(
                    color = Color.White,
                    radius = comRadiusPx,
                    center = Offset(comX, comY),
                    style = Stroke(width = comOutlinePx),
                )
            }
        }
    }
}

/** Phase-to-color mapping for dynamic skeleton overlay. */
private fun phaseColor(phase: Phase): Color = when (phase) {
    Phase.APPROACH -> Color.White
    Phase.FLIGHT -> Color(0xFF29B6F6)  // Arctic Sky cyan
    Phase.LANDING -> Color(0xFFFFBF00) // amber
}

/**
 * A Compose [Canvas] composable that draws an H3.6M skeleton overlay
 * driven by real pose data from the backend, with phase-based coloring.
 *
 * Converts [currentFrameMs] to a frame index, interpolates pose keypoints,
 * determines the skating phase, and renders bones/joints with phase-dependent colors.
 *
 * @param poseData Pose data from backend (keyframes + fps).
 * @param currentFrameMs Current video playback position in milliseconds.
 * @param phases Phase boundaries (may be null if analysis not complete).
 * @param videoWidth Video width in pixels (unused — coords are normalized).
 * @param videoHeight Video height in pixels (unused — coords are normalized).
 * @param showOverlay Whether the overlay is visible.
 * @param modifier Standard modifier.
 */
@Composable
fun DynamicSkeletonOverlay(
    poseData: PoseData,
    currentFrameMs: Long,
    phases: PhasesData?,
    videoWidth: Int,
    videoHeight: Int,
    showOverlay: Boolean,
    modifier: Modifier = Modifier,
) {
    if (!showOverlay) return

    val density = LocalDensity.current
    val jointRadiusPx = with(density) { JOINT_RADIUS_DP.toPx() }
    val boneWidthPx = with(density) { BONE_WIDTH_DP.toPx() }

    // Convert playback time to frame index
    val frameIndex = ((currentFrameMs / 1000.0) * poseData.fps).toInt()

    // Interpolate keypoints at this frame
    val keypoints = interpolatePose(poseData.poses, keyframeInterval = 10, frameIndex = frameIndex)

    // Determine phase for coloring
    val phase = phaseForFrame(phases, frameIndex)
    val boneColor = if (phase != null) phaseColor(phase).copy(alpha = 0.7f) else BONE_COLOR
    val jointBaseColor = if (phase != null) phaseColor(phase) else Color.White

    Canvas(modifier = modifier) {
        if (keypoints == null) return@Canvas
        if (keypoints.size < 17) return@Canvas

        val w = size.width
        val h = size.height

        // Draw skeleton bones
        for ((start, end) in H36M_CONNECTIONS) {
            val kpStart = keypoints[start]
            val kpEnd = keypoints[end]
            if (kpStart == null || kpEnd == null) continue
            if (kpStart.confidence < DEFAULT_CONFIDENCE_THRESHOLD) continue
            if (kpEnd.confidence < DEFAULT_CONFIDENCE_THRESHOLD) continue

            drawLine(
                color = boneColor,
                start = Offset(kpStart.x * w, kpStart.y * h),
                end = Offset(kpEnd.x * w, kpEnd.y * h),
                strokeWidth = boneWidthPx,
            )
        }

        // Draw joint circles
        for (i in keypoints.indices) {
            val kp = keypoints[i] ?: continue
            if (kp.confidence < DEFAULT_CONFIDENCE_THRESHOLD) continue

            drawCircle(
                color = jointBaseColor,
                radius = jointRadiusPx,
                center = Offset(kp.x * w, kp.y * h),
            )
        }
    }
}
