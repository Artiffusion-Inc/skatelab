// AUTO-GENERATED — do not edit. Source: DESIGN.md
package ru.skatelab.capture.presentation.theme

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

object SkateLabModifiers {
    private val roundedXs = RoundedCornerShape(4.dp)
    private val roundedSm = RoundedCornerShape(6.dp)
    private val roundedMd = RoundedCornerShape(12.dp)
    private val roundedLg = RoundedCornerShape(16.dp)
    private val roundedXl = RoundedCornerShape(20.dp)
    private val rounded2xl = RoundedCornerShape(30.dp)
    private val roundedFull = RoundedCornerShape(9999.dp)

    // Buttons
    val buttonPrimaryDark: Modifier
        get() =
            Modifier
                .background(SkateLabColors.primary, roundedMd)
                .padding(horizontal = 20.dp, vertical = 12.dp)

    val buttonPrimaryDarkPressed: Modifier
        get() =
            Modifier
                .background(SkateLabColors.primaryDeep, roundedMd)
                .padding(horizontal = 20.dp, vertical = 12.dp)

    val buttonOnDarkPill: Modifier
        get() =
            Modifier
                .background(SkateLabColors.surfaceIceSoft, roundedFull)
                .padding(horizontal = 20.dp, vertical = 12.dp)

    val buttonSecondaryOutline: Modifier
        get() =
            Modifier
                .background(SkateLabColors.canvas, roundedMd)
                .border(1.dp, SkateLabColors.hairlineDark, roundedMd)
                .padding(horizontal = 20.dp, vertical = 12.dp)

    val buttonOnTeal: Modifier
        get() =
            Modifier
                .background(SkateLabColors.canvas, roundedMd)
                .padding(horizontal = 20.dp, vertical = 12.dp)

    val buttonGhost: Modifier
        get() =
            Modifier
                .background(Color.Transparent, roundedMd)
                .padding(horizontal = 20.dp, vertical = 12.dp)

    // Inputs
    val textInput: Modifier
        get() =
            Modifier
                .background(SkateLabColors.canvas, roundedSm)
                .border(1.dp, SkateLabColors.hairline, roundedSm)
                .padding(horizontal = 12.dp, vertical = 10.dp)

    // Cards
    val cardFeatureLight: Modifier
        get() =
            Modifier
                .background(SkateLabColors.canvas, roundedLg)
                .padding(32.dp)

    val cardTealBand: Modifier
        get() =
            Modifier
                .background(SkateLabColors.surfaceTealDeep, roundedLg)
                .padding(64.dp)

    // Badge
    val badgeOpaque: Modifier
        get() =
            Modifier
                .background(
                    color = SkateLabColors.primaryDeep.copy(alpha = 0.85f),
                    shape = roundedMd,
                )
                .border(
                    width = 1.dp,
                    color = SkateLabColors.surfaceIceSoft.copy(alpha = 0.4f),
                    shape = roundedMd,
                )
                .padding(horizontal = 16.dp, vertical = 12.dp)

    // Navigation & Tabs
    val pillTabLight: Modifier
        get() =
            Modifier
                .background(SkateLabColors.canvas, roundedFull)
                .padding(horizontal = 16.dp, vertical = 8.dp)

    val navBarDark: Modifier
        get() =
            Modifier
                .background(SkateLabColors.primary, roundedXs)
                .padding(horizontal = 24.dp, vertical = 16.dp)

    val navBarLight: Modifier
        get() =
            Modifier
                .background(SkateLabColors.canvas, roundedXs)
                .padding(horizontal = 24.dp, vertical = 16.dp)

    val footerLight: Modifier
        get() =
            Modifier
                .background(SkateLabColors.canvas, roundedXs)
                .padding(horizontal = 24.dp, vertical = 64.dp)

    // Shadow references
    val shadowAmbientLow: Modifier
        get() = SkateLabShadows.ambientLow

    val shadowAmbientMedium: Modifier
        get() = SkateLabShadows.ambientMedium

    val shadowAmbientHigh: Modifier
        get() = SkateLabShadows.ambientHigh
}
