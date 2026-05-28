package ru.skatelab.shared.utils

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class PoseInterpolationTest {
    private val poses = listOf(
        listOf(listOf(0.1f, 0.2f, 0.9f), listOf(0.3f, 0.4f, 0.8f)),
        listOf(listOf(0.5f, 0.6f, 0.9f), listOf(0.7f, 0.8f, 0.7f)),
        listOf(listOf(0.9f, 1.0f, 0.9f), listOf(0.1f, 0.2f, 0.6f)),
    )

    @Test
    fun interpolate_exactKeyframe_returnsOriginal() {
        val result = interpolatePose(poses, keyframeInterval = 10, frameIndex = 0)
        assertEquals(0.1f, result!![0]!![0])
        assertEquals(0.2f, result[0]!![1])
    }

    @Test
    fun interpolate_betweenKeyframes_returnsLinearBlend() {
        val result = interpolatePose(poses, keyframeInterval = 10, frameIndex = 5)
        assertEquals(0.3f, result!![0]!![0], 0.01f)
        assertEquals(0.4f, result[0]!![1], 0.01f)
    }

    @Test
    fun interpolate_lowConfidence_returnsNullKeypoint() {
        val lowConfPoses = listOf(
            listOf(listOf(0.1f, 0.2f, 0.2f)),
            listOf(listOf(0.5f, 0.6f, 0.9f)),
        )
        val result = interpolatePose(lowConfPoses, keyframeInterval = 10, frameIndex = 5)
        // min(0.2, 0.9) = 0.2 < 0.3 threshold → null keypoint
        assertNull(result!![0])
    }

    @Test
    fun interpolate_pastLastKeyframe_returnsLastKeyframe() {
        val result = interpolatePose(poses, keyframeInterval = 10, frameIndex = 25)
        assertEquals(0.9f, result!![0]!![0])
    }

    @Test
    fun interpolate_emptyPoses_returnsNull() {
        val result = interpolatePose(emptyList(), keyframeInterval = 10, frameIndex = 0)
        assertNull(result)
    }

    @Test
    fun interpolate_negativeFrameIndex_returnsFirstKeyframe() {
        val result = interpolatePose(poses, keyframeInterval = 10, frameIndex = -5)
        assertEquals(0.1f, result!![0]!![0])
    }

    @Test
    fun interpolate_lastKeypointLowConfidence_returnsNull() {
        val poses2 = listOf(
            listOf(listOf(0.5f, 0.5f, 0.9f), listOf(0.3f, 0.4f, 0.2f)),
            listOf(listOf(0.7f, 0.7f, 0.9f), listOf(0.5f, 0.6f, 0.1f)),
        )
        val result = interpolatePose(poses2, keyframeInterval = 10, frameIndex = 5)
        assertEquals(0.6f, result!![0]!![0], 0.01f)
        assertNull(result[1]) // conf 0.2 at floor, 0.1 at ceil → min=0.1 < 0.3
    }
}
