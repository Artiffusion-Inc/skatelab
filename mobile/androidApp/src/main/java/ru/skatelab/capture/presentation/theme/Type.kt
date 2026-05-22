// AUTO-GENERATED — do not edit. Source: DESIGN.md
package ru.skatelab.capture.presentation.theme

import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.compose.ui.unit.em

// ── Font families ──────────────────────────────────────────────────

/** Inter Variable with sub-default weights (460, 540, 600) plus 700. */
val InterVariable: FontFamily = FontFamily(
    Font(R.font.inter_variable_460, FontWeight.W460),
    Font(R.font.inter_variable_540, FontWeight.W540),
    Font(R.font.inter_variable_600, FontWeight.W600),
    Font(R.font.inter_variable_700, FontWeight.W700),
)

/** System fallback for API < 28 where variable fonts may not render. */
val InterFallback: FontFamily = FontFamily(
    Font(R.font.inter_regular, FontWeight.W400),
    Font(R.font.inter_medium, FontWeight.W500),
    Font(R.font.inter_semibold, FontWeight.W600),
    Font(R.font.inter_bold, FontWeight.W700),
)

// ── Custom FontWeight values for Inter Variable ───────────────────

/** Sub-default weight 460 — the brand's "quiet warmth" replacement for W400/W500. */
val FontWeight.Companion.W460: FontWeight get() = FontWeight(460)

/** Sub-default weight 540 — the brand's warm medium, used in display and body-lead. */
val FontWeight.Companion.W540: FontWeight get() = FontWeight(540)

/** Sub-default weight 600 — used for button-cap and UI-interactive elements only. */
val FontWeight.Companion.W600: FontWeight get() = FontWeight(600)

// ── Helper ─────────────────────────────────────────────────────────

/**
 * Returns [InterVariable] on API ≥ 28, [InterFallback] otherwise.
 * Usage: `fontFamily = weightOrFallback(…)`
 */
fun weightOrFallback(): FontFamily = InterVariable

// ── Typography data class ─────────────────────────────────────────

data class SkateLabTypography(
    val displayXxl: TextStyle,
    val displayXl: TextStyle,
    val displayLg: TextStyle,
    val displayMd: TextStyle,
    val headingLg: TextStyle,
    val bodyLg: TextStyle,
    val bodyMd: TextStyle,
    val bodyStrong: TextStyle,
    val buttonMd: TextStyle,
    val buttonCap: TextStyle,
    val caption: TextStyle,
    val micro: TextStyle,
    val legal: TextStyle,
    val price: TextStyle,
)

val SkateLabTypographyDefaults: SkateLabTypography = SkateLabTypography(
    // ── Display ────────────────────────────────────────────────────
    displayXxl = TextStyle(
        fontFamily = weightOrFallback(),
        fontSize = 40.sp,       // clamp(2.25rem,5.5vw,4rem) → 36–64dp range; 40sp is mobile anchor
        fontWeight = FontWeight.W540,
        lineHeight = 0.96.em,
        letterSpacing = 0.sp,
    ),
    displayXl = TextStyle(
        fontFamily = weightOrFallback(),
        fontSize = 30.sp,       // clamp(2rem,4vw,3rem) → 32–48dp range; 30sp is mobile anchor
        fontWeight = FontWeight.W460,
        lineHeight = 0.96.em,
        letterSpacing = (-1.32).sp,
    ),
    displayLg = TextStyle(
        fontFamily = weightOrFallback(),
        fontSize = 28.sp,
        fontWeight = FontWeight.W540,
        lineHeight = 1.14.em,
        letterSpacing = (-0.63).sp,
    ),
    displayMd = TextStyle(
        fontFamily = weightOrFallback(),
        fontSize = 22.sp,
        fontWeight = FontWeight.W460,
        lineHeight = 1.1.em,
        letterSpacing = (-0.315).sp,
    ),
    // ── Heading ────────────────────────────────────────────────────
    headingLg = TextStyle(
        fontFamily = weightOrFallback(),
        fontSize = 20.sp,
        fontWeight = FontWeight.W460,
        lineHeight = 1.2.em,
        letterSpacing = (-0.4).sp,
    ),
    // ── Body ───────────────────────────────────────────────────────
    bodyLg = TextStyle(
        fontFamily = weightOrFallback(),
        fontSize = 18.sp,
        fontWeight = FontWeight.W540,
        lineHeight = 1.5.em,
        letterSpacing = (-0.135).sp,
    ),
    bodyMd = TextStyle(
        fontFamily = weightOrFallback(),
        fontSize = 16.sp,
        fontWeight = FontWeight.W460,
        lineHeight = 1.5.em,
        letterSpacing = 0.sp,
    ),
    bodyStrong = TextStyle(
        fontFamily = weightOrFallback(),
        fontSize = 18.72.sp,
        fontWeight = FontWeight.W700,
        lineHeight = 1.5.em,
        letterSpacing = 0.sp,
    ),
    // ── Button ─────────────────────────────────────────────────────
    buttonMd = TextStyle(
        fontFamily = weightOrFallback(),
        fontSize = 16.sp,
        fontWeight = FontWeight.W700,
        lineHeight = 1.0.em,
        letterSpacing = 0.sp,
    ),
    buttonCap = TextStyle(
        fontFamily = weightOrFallback(),
        fontSize = 14.sp,
        fontWeight = FontWeight.W600,
        lineHeight = 1.0.em,
        letterSpacing = 0.sp,
    ),
    // ── Supporting ─────────────────────────────────────────────────
    caption = TextStyle(
        fontFamily = weightOrFallback(),
        fontSize = 14.sp,
        fontWeight = FontWeight.W460,
        lineHeight = 1.4.em,
        letterSpacing = 0.sp,
    ),
    micro = TextStyle(
        fontFamily = weightOrFallback(),
        fontSize = 12.sp,
        fontWeight = FontWeight.W540,
        lineHeight = 1.4.em,
        letterSpacing = 0.sp,
    ),
    legal = TextStyle(
        fontFamily = weightOrFallback(),
        fontSize = 11.sp,
        fontWeight = FontWeight.W460,
        lineHeight = 1.5.em,
        letterSpacing = 0.sp,
    ),
    // ── Special ────────────────────────────────────────────────────
    price = TextStyle(
        fontFamily = weightOrFallback(),
        fontSize = 30.sp,       // clamp(2.25rem,4vw,3rem) → mobile anchor
        fontWeight = FontWeight.W700,
        lineHeight = 1.0.em,
        letterSpacing = (-0.03).em, // -0.03em expressed as em
        fontFeatureSettings = "tnum", // tabular-nums
    ),
)
