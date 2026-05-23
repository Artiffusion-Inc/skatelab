// AUTO-GENERATED — do not edit. Source: DESIGN.md
package ru.skatelab.capture.presentation.theme

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

object SkateLabModifiers {
    // Rounded shapes
    val roundedXs = RoundedCornerShape(4.dp)
    val roundedSm = RoundedCornerShape(6.dp)
    val roundedMd = RoundedCornerShape(12.dp)
    val roundedLg = RoundedCornerShape(16.dp)
    val roundedXl = RoundedCornerShape(20.dp)
    val rounded2xl = RoundedCornerShape(30.dp)
    val roundedFull = RoundedCornerShape(percent = 50)

    // Spacing scale
    val spaceXxs = 2.dp
    val spaceXs = 4.dp
    val spaceSm = 8.dp
    val spaceMd = 12.dp
    val spaceLg = 16.dp
    val spaceXl = 24.dp
    val spaceXxl = 32.dp
    val spaceHuge = 64.dp

    // Component modifiers (15 component token sets)
    fun Modifier.cardFeatureLight(): Modifier =
        this
            .clip(roundedLg)
            .background(SkateLabColors.canvas)
            .padding(32.dp)

    fun Modifier.cardTealBand(): Modifier =
        this
            .clip(roundedLg)
            .background(SkateLabColors.surfaceTealDeep)
            .padding(64.dp)

    fun Modifier.textInput(): Modifier =
        this
            .clip(roundedSm)
            .background(SkateLabColors.canvas)
            .border(1.dp, SkateLabColors.hairline, roundedSm)
            .padding(horizontal = 12.dp, vertical = 10.dp)

    fun Modifier.badgeOpaque(): Modifier =
        this
            .clip(roundedMd)
            .background(Color(0xD90E3340))
            .border(1.dp, Color(0x66C8E6F0), roundedMd)
            .padding(horizontal = 16.dp, vertical = 12.dp)

    fun Modifier.buttonPrimaryDark(): Modifier =
        this
            .clip(roundedMd)
            .background(SkateLabColors.primary)
            .padding(horizontal = 20.dp, vertical = 12.dp)

    fun Modifier.buttonPrimaryDarkPressed(): Modifier =
        this
            .clip(roundedMd)
            .background(SkateLabColors.primaryDeep)
            .padding(horizontal = 20.dp, vertical = 12.dp)

    fun Modifier.buttonOnDarkPill(): Modifier =
        this
            .clip(roundedFull)
            .background(SkateLabColors.surfaceIceSoft)
            .padding(horizontal = 20.dp, vertical = 12.dp)

    fun Modifier.buttonSecondaryOutline(): Modifier =
        this
            .clip(roundedMd)
            .background(SkateLabColors.canvas)
            .border(1.dp, SkateLabColors.hairlineDark, roundedMd)
            .padding(horizontal = 20.dp, vertical = 12.dp)

    fun Modifier.buttonOnTeal(): Modifier =
        this
            .clip(roundedMd)
            .background(SkateLabColors.canvas)
            .padding(horizontal = 20.dp, vertical = 12.dp)

    fun Modifier.buttonGhost(): Modifier =
        this
            .clip(roundedMd)
            .background(Color.Transparent)
            .padding(horizontal = 20.dp, vertical = 12.dp)

    fun Modifier.buttonDestructive(): Modifier =
        this
            .clip(roundedMd)
            .background(Color(0x1AC0392B))
            .padding(horizontal = 20.dp, vertical = 12.dp)

    fun Modifier.pillTabLight(): Modifier =
        this
            .clip(roundedFull)
            .background(SkateLabColors.canvas)
            .padding(horizontal = 16.dp, vertical = 8.dp)

    fun Modifier.navBarDark(): Modifier =
        this
            .clip(roundedXs)
            .background(SkateLabColors.primary)
            .padding(horizontal = 24.dp, vertical = 16.dp)

    fun Modifier.navBarLight(): Modifier =
        this
            .clip(roundedXs)
            .background(SkateLabColors.canvas)
            .padding(horizontal = 24.dp, vertical = 16.dp)

    fun Modifier.footerLight(): Modifier =
        this
            .clip(roundedXs)
            .background(SkateLabColors.canvas)
            .padding(horizontal = 24.dp, vertical = 64.dp)
}
