// AUTO-GENERATED — do not edit. Source: DESIGN.md
package ru.skatelab.capture.presentation.theme

import android.os.Build
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import ru.skatelab.capture.R

val InterVariable =
    FontFamily(
        Font(R.font.inter_variable, FontWeight.Normal),
    )

val InterFallback =
    FontFamily(
        Font(R.font.inter_regular, FontWeight.Normal),
        Font(R.font.inter_medium, FontWeight.Medium),
        Font(R.font.inter_semibold, FontWeight.SemiBold),
        Font(R.font.inter_bold, FontWeight.Bold),
    )

fun weightOrFallback(requested: Int): FontWeight {
    return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
        FontWeight(requested)
    } else {
        when {
            requested < 500 -> FontWeight.Normal
            requested < 600 -> FontWeight.Medium
            requested < 700 -> FontWeight.SemiBold
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
                fontFamily = InterVariable,
                fontSize = 64.sp,
                fontWeight = weightOrFallback(540),
                lineHeight = 0.96.em,
                letterSpacing = 0.sp,
            ),
        displayXl =
            TextStyle(
                fontFamily = InterVariable,
                fontSize = 48.sp,
                fontWeight = weightOrFallback(460),
                lineHeight = 0.96.em,
                letterSpacing = (-1.32).sp,
            ),
        displayLg =
            TextStyle(
                fontFamily = InterVariable,
                fontSize = 28.sp,
                fontWeight = weightOrFallback(540),
                lineHeight = 1.14.em,
                letterSpacing = (-0.63).sp,
            ),
        displayMd =
            TextStyle(
                fontFamily = InterVariable,
                fontSize = 22.sp,
                fontWeight = weightOrFallback(460),
                lineHeight = 1.1.em,
                letterSpacing = (-0.315).sp,
            ),
        headingLg =
            TextStyle(
                fontFamily = InterVariable,
                fontSize = 20.sp,
                fontWeight = weightOrFallback(460),
                lineHeight = 1.2.em,
                letterSpacing = (-0.4).sp,
            ),
        bodyLg =
            TextStyle(
                fontFamily = InterVariable,
                fontSize = 18.sp,
                fontWeight = weightOrFallback(540),
                lineHeight = 1.5.em,
                letterSpacing = (-0.135).sp,
            ),
        bodyMd =
            TextStyle(
                fontFamily = InterVariable,
                fontSize = 16.sp,
                fontWeight = weightOrFallback(460),
                lineHeight = 1.5.em,
                letterSpacing = 0.sp,
            ),
        bodyStrong =
            TextStyle(
                fontFamily = InterVariable,
                fontSize = 18.72.sp,
                fontWeight = weightOrFallback(700),
                lineHeight = 1.5.em,
                letterSpacing = 0.sp,
            ),
        buttonMd =
            TextStyle(
                fontFamily = InterVariable,
                fontSize = 16.sp,
                fontWeight = weightOrFallback(700),
                lineHeight = 1.0.em,
                letterSpacing = 0.sp,
            ),
        buttonCap =
            TextStyle(
                fontFamily = InterVariable,
                fontSize = 14.sp,
                fontWeight = weightOrFallback(600),
                lineHeight = 1.0.em,
                letterSpacing = 0.sp,
            ),
        caption =
            TextStyle(
                fontFamily = InterVariable,
                fontSize = 14.sp,
                fontWeight = weightOrFallback(460),
                lineHeight = 1.4.em,
                letterSpacing = 0.sp,
            ),
        micro =
            TextStyle(
                fontFamily = InterVariable,
                fontSize = 12.sp,
                fontWeight = weightOrFallback(540),
                lineHeight = 1.4.em,
                letterSpacing = 0.sp,
            ),
        legal =
            TextStyle(
                fontFamily = InterVariable,
                fontSize = 11.sp,
                fontWeight = weightOrFallback(460),
                lineHeight = 1.5.em,
                letterSpacing = 0.sp,
            ),
        price =
            TextStyle(
                fontFamily = InterVariable,
                fontSize = 48.sp,
                fontWeight = weightOrFallback(700),
                lineHeight = 1.0.em,
                letterSpacing = (-0.03).em,
            ),
    )
