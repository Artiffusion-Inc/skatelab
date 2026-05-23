// AUTO-GENERATED — do not edit. Source: DESIGN.md
package ru.skatelab.capture.presentation.theme

import android.os.Build
import androidx.annotation.OptIn
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.ExperimentalResourceApi
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import ru.skatelab.capture.R

@OptIn(ExperimentalResourceApi::class)
private val InterVariable =
    FontFamily(
        Font(
            resId = R.font.inter_variable,
            variationSettings =
                FontVariation.Settings(
                    FontVariation.weight(400),
                    FontVariation.slant(0f),
                ),
        ),
    )

private val InterFallback =
    FontFamily(
        Font(R.font.inter_regular, FontWeight.Normal),
        Font(R.font.inter_medium, FontWeight.Medium),
        Font(R.font.inter_semibold, FontWeight.SemiBold),
        Font(R.font.inter_bold, FontWeight.Bold),
    )

private val SkateLabFontFamily: FontFamily =
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
        InterVariable
    } else {
        InterFallback
    }

fun weightOrFallback(desired: Int): FontWeight {
    return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
        FontWeight(desired)
    } else {
        when (desired) {
            in 0..450 -> FontWeight.Normal
            in 451..550 -> FontWeight.Medium
            in 551..650 -> FontWeight.SemiBold
            else -> FontWeight.Bold
        }
    }
}

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

val SkateLabTypographyDefaults =
    SkateLabTypography(
        displayXxl =
            TextStyle(
                fontFamily = SkateLabFontFamily,
                fontSize = 36.sp,
                fontWeight = weightOrFallback(540),
                lineHeight = 0.96.em,
                letterSpacing = 0.sp,
            ),
        displayXl =
            TextStyle(
                fontFamily = SkateLabFontFamily,
                fontSize = 32.sp,
                fontWeight = weightOrFallback(460),
                lineHeight = 0.96.em,
                letterSpacing = (-1.32).sp,
            ),
        displayLg =
            TextStyle(
                fontFamily = SkateLabFontFamily,
                fontSize = 28.sp,
                fontWeight = weightOrFallback(540),
                lineHeight = 1.14.em,
                letterSpacing = (-0.63).sp,
            ),
        displayMd =
            TextStyle(
                fontFamily = SkateLabFontFamily,
                fontSize = 22.sp,
                fontWeight = weightOrFallback(460),
                lineHeight = 1.1.em,
                letterSpacing = (-0.315).sp,
            ),
        headingLg =
            TextStyle(
                fontFamily = SkateLabFontFamily,
                fontSize = 20.sp,
                fontWeight = weightOrFallback(460),
                lineHeight = 1.2.em,
                letterSpacing = (-0.4).sp,
            ),
        bodyLg =
            TextStyle(
                fontFamily = SkateLabFontFamily,
                fontSize = 18.sp,
                fontWeight = weightOrFallback(540),
                lineHeight = 1.5.em,
                letterSpacing = (-0.135).sp,
            ),
        bodyMd =
            TextStyle(
                fontFamily = SkateLabFontFamily,
                fontSize = 16.sp,
                fontWeight = weightOrFallback(460),
                lineHeight = 1.5.em,
                letterSpacing = 0.sp,
            ),
        bodyStrong =
            TextStyle(
                fontFamily = SkateLabFontFamily,
                fontSize = 18.72.sp,
                fontWeight = weightOrFallback(700),
                lineHeight = 1.5.em,
                letterSpacing = 0.sp,
            ),
        buttonMd =
            TextStyle(
                fontFamily = SkateLabFontFamily,
                fontSize = 16.sp,
                fontWeight = weightOrFallback(700),
                lineHeight = 1.0.em,
                letterSpacing = 0.sp,
            ),
        buttonCap =
            TextStyle(
                fontFamily = SkateLabFontFamily,
                fontSize = 14.sp,
                fontWeight = weightOrFallback(600),
                lineHeight = 1.0.em,
                letterSpacing = 0.sp,
            ),
        caption =
            TextStyle(
                fontFamily = SkateLabFontFamily,
                fontSize = 14.sp,
                fontWeight = weightOrFallback(460),
                lineHeight = 1.4.em,
                letterSpacing = 0.sp,
            ),
        micro =
            TextStyle(
                fontFamily = SkateLabFontFamily,
                fontSize = 12.sp,
                fontWeight = weightOrFallback(540),
                lineHeight = 1.4.em,
                letterSpacing = 0.sp,
            ),
        legal =
            TextStyle(
                fontFamily = SkateLabFontFamily,
                fontSize = 11.sp,
                fontWeight = weightOrFallback(460),
                lineHeight = 1.5.em,
                letterSpacing = 0.sp,
            ),
        price =
            TextStyle(
                fontFamily = SkateLabFontFamily,
                fontSize = 36.sp,
                fontWeight = weightOrFallback(700),
                lineHeight = 1.0.em,
                letterSpacing = (-0.03).em,
            ),
    )
