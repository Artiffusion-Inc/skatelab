// AUTO-GENERATED — do not edit. Source: DESIGN.md
package ru.skatelab.capture.presentation.theme

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

/**
 * Convenience modifiers derived from design-system component tokens.
 *
 * These combine background + shape + border + padding into reusable Modifier
 * chains so that screens stay consistent with DESIGN.md.
 */
object SkateLabModifiers {

    // ── Rounded shapes (from DESIGN.md rounded tokens) ─────────────
    val shapeXs   = RoundedCornerShape(4.dp)
    val shapeSm   = RoundedCornerShape(6.dp)
    val shapeMd   = RoundedCornerShape(12.dp)
    val shapeLg   = RoundedCornerShape(16.dp)
    val shapeXl   = RoundedCornerShape(20.dp)
    val shape2xl  = RoundedCornerShape(30.dp)
    val shapeFull = RoundedCornerShape(50)  // pill / full

    // ── Spacing (from DESIGN.md spacing tokens) ────────────────────
    val spacingXxs  = 2.dp
    val spacingXs   = 4.dp
    val spacingSm   = 8.dp
    val spacingMd   = 12.dp
    val spacingLg   = 16.dp
    val spacingXl   = 24.dp
    val spacingXxl  = 32.dp
    val spacingHuge = 64.dp

    // ── Button: primary-dark ────────────────────────────────────────
    val buttonPrimaryDark = Modifier
        .background(SkateLabColors.primary, shapeMd)
        .padding(horizontal = 20.dp, vertical = 12.dp)

    // ── Button: primary-dark-pressed ───────────────────────────────
    val buttonPrimaryDarkPressed = Modifier
        .background(SkateLabColors.primaryDeep, shapeMd)
        .padding(horizontal = 20.dp, vertical = 12.dp)

    // ── Button: on-dark-pill (hero only) ───────────────────────────
    val buttonOnDarkPill = Modifier
        .background(SkateLabColors.surfaceIceSoft, shapeFull)
        .padding(horizontal = 20.dp, vertical = 12.dp)

    // ── Button: secondary-outline ───────────────────────────────────
    val buttonSecondaryOutline = Modifier
        .background(SkateLabColors.canvas, shapeMd)
        .border(1.dp, SkateLabColors.hairlineDark, shapeMd)
        .padding(horizontal = 20.dp, vertical = 12.dp)

    // ── Button: on-teal (inside teal closing band) ──────────────────
    val buttonOnTeal = Modifier
        .background(SkateLabColors.canvas, shapeMd)
        .padding(horizontal = 20.dp, vertical = 12.dp)

    // ── Button: ghost ──────────────────────────────────────────────
    val buttonGhost = Modifier
        .padding(horizontal = 20.dp, vertical = 12.dp)

    // ── Text input ─────────────────────────────────────────────────
    val textInput = Modifier
        .background(SkateLabColors.canvas, shapeSm)
        .border(1.dp, SkateLabColors.hairline, shapeSm)
        .padding(horizontal = 12.dp, vertical = 10.dp)

    // ── Card: feature-light ─────────────────────────────────────────
    val cardFeatureLight = Modifier
        .background(SkateLabColors.canvas, shapeLg)
        .border(1.dp, SkateLabColors.hairline, shapeLg)
        .padding(32.dp)

    // ── Card: teal-band (closing CTA) ──────────────────────────────
    val cardTealBand = Modifier
        .background(SkateLabColors.surfaceTealDeep, shapeLg)
        .padding(64.dp)

    // ── Badge: opaque ──────────────────────────────────────────────
    val badgeOpaque = Modifier
        .background(Color(0xD94D5C68), shapeMd) // oklch(0.301 0.047 225 / 0.85) ≈ #4D5C68 @85%
        .border(1.dp, Color(0x66C8E6F0), shapeMd) // oklch(0.906 0.034 220 / 0.4) ≈ #C8E6F0 @40%
        .padding(horizontal = 16.dp, vertical = 12.dp)

    // ── Pill-tab-light ─────────────────────────────────────────────
    val pillTabLight = Modifier
        .background(SkateLabColors.canvas, shapeFull)
        .padding(horizontal = 16.dp, vertical = 8.dp)

    // ── Nav-bar: dark ──────────────────────────────────────────────
    val navBarDark = Modifier
        .background(SkateLabColors.primary, shapeXs)
        .padding(horizontal = 24.dp, vertical = 16.dp)

    // ── Nav-bar: light ──────────────────────────────────────────────
    val navBarLight = Modifier
        .background(SkateLabColors.canvas, shapeXs)
        .padding(horizontal = 24.dp, vertical = 16.dp)

    // ── Footer: light ─────────────────────────────────────────────
    val footerLight = Modifier
        .background(SkateLabColors.canvas, shapeXs)
        .padding(horizontal = 24.dp, vertical = 64.dp)

    // ── Metric card ────────────────────────────────────────────────
    val metricCard = Modifier
        .background(SkateLabColors.canvas, shapeMd)
        .border(1.dp, SkateLabColors.hairline, shapeMd)
}
