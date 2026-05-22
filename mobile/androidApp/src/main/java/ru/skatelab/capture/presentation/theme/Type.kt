// AUTO-GENERATED — do not edit. Source: DESIGN.md
// Regenerate: task design:build

package ru.skatelab.capture.presentation.theme

import android.os.Build
import androidx.annotation.RequiresApi
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

@RequiresApi(Build.VERSION_CODES.O)
val InterVariable =
    FontFamily(
        Font(R.font.inter_variable, FontWeight(460), FontVariation.Settings(FontVariation.weight(460))),
        Font(R.font.inter_variable, FontWeight(540), FontVariation.Settings(FontVariation.weight(540))),
        Font(R.font.inter_variable, FontWeight(600), FontVariation.Settings(FontVariation.weight(600))),
        Font(R.font.inter_variable, FontWeight(700), FontVariation.Settings(FontVariation.weight(700))),
    )

// Fallback for API < 28: static Inter weights
val InterFallback =
    FontFamily(
        Font(R.font.inter_regular, FontWeight.Normal), // 400
        Font(R.font.inter_medium, FontWeight.Medium), // 500
        Font(R.font.inter_semibold, FontWeight.SemiBold), // 600
        Font(R.font.inter_bold, FontWeight.Bold), // 700
    )

val AppFontFamily = if (Build.VERSION.SDK_INT >= 28) InterVariable else InterFallback

@OptIn(ExperimentalTextApi::class)
data class SkateLabTypography(
    val displayXxl: TextStyle =
        TextStyle(
            fontFamily = AppFontFamily,
            fontSize = 36.sp,
            fontWeight = weightOrFallback(540, FontWeight.SemiBold),
            lineHeight = 34.56.sp,
        ),
    val displayXl: TextStyle =
        TextStyle(
            fontFamily = AppFontFamily,
            fontSize = 32.sp,
            fontWeight = weightOrFallback(460, FontWeight.Normal),
            lineHeight = 30.72.sp,
            letterSpacing = (-1.32).sp,
        ),
    val displayLg: TextStyle =
        TextStyle(
            fontFamily = AppFontFamily,
            fontSize = 28.sp,
            fontWeight = weightOrFallback(540, FontWeight.SemiBold),
            lineHeight = 31.92.sp,
            letterSpacing = (-0.63).sp,
        ),
    val displayMd: TextStyle =
        TextStyle(
            fontFamily = AppFontFamily,
            fontSize = 22.sp,
            fontWeight = weightOrFallback(460, FontWeight.Normal),
            lineHeight = 24.2.sp,
            letterSpacing = (-0.315).sp,
        ),
    val headingLg: TextStyle =
        TextStyle(
            fontFamily = AppFontFamily,
            fontSize = 20.sp,
            fontWeight = weightOrFallback(460, FontWeight.Normal),
            lineHeight = 24.sp,
            letterSpacing = (-0.4).sp,
        ),
    val bodyLg: TextStyle =
        TextStyle(
            fontFamily = AppFontFamily,
            fontSize = 18.sp,
            fontWeight = weightOrFallback(540, FontWeight.SemiBold),
            lineHeight = 27.sp,
            letterSpacing = (-0.135).sp,
        ),
    val bodyMd: TextStyle =
        TextStyle(fontFamily = AppFontFamily, fontSize = 16.sp, fontWeight = weightOrFallback(460, FontWeight.Normal), lineHeight = 24.sp),
    val bodyStrong: TextStyle =
        TextStyle(fontFamily = AppFontFamily, fontSize = 18.72.sp, fontWeight = FontWeight.Bold, lineHeight = 28.08.sp),
    val buttonMd: TextStyle = TextStyle(fontFamily = AppFontFamily, fontSize = 16.sp, fontWeight = FontWeight.Bold, lineHeight = 16.sp),
    val buttonCap: TextStyle =
        TextStyle(fontFamily = AppFontFamily, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, lineHeight = 14.sp),
    val caption: TextStyle =
        TextStyle(
            fontFamily = AppFontFamily,
            fontSize = 14.sp,
            fontWeight = weightOrFallback(460, FontWeight.Normal),
            lineHeight = 19.6.sp,
        ),
    val micro: TextStyle =
        TextStyle(
            fontFamily = AppFontFamily,
            fontSize = 12.sp,
            fontWeight = weightOrFallback(540, FontWeight.SemiBold),
            lineHeight = 16.8.sp,
        ),
    val legal: TextStyle =
        TextStyle(
            fontFamily = AppFontFamily,
            fontSize = 11.sp,
            fontWeight = weightOrFallback(460, FontWeight.Normal),
            lineHeight = 16.5.sp,
        ),
    val price: TextStyle =
        TextStyle(
            fontFamily = AppFontFamily,
            fontSize = 32.sp,
            fontWeight = FontWeight.Bold,
            lineHeight = 32.sp,
            letterSpacing = (-0.96).sp,
            fontFeatureSettings = "tnum",
        ),
)

private fun weightOrFallback(
    variable: Int,
    fallback: FontWeight,
): FontWeight = if (Build.VERSION.SDK_INT >= 28) FontWeight(variable) else fallback

val SkateLabTypographyDefaults = SkateLabTypography()
