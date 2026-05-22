// AUTO-GENERATED — do not edit. Source: DESIGN.md
// Regenerate: task design:build

import SwiftUI

@available(iOS 15, *)
struct SkateLabColorScheme {
    let primary = Color.skatePrimary
    let primaryDeep = Color.skatePrimaryDeep
    let primaryForeground = Color.skatePrimaryForeground
    let ink = Color.skateInk
    let inkMute = Color.skateInkMute
    let inkFaint = Color.skateInkFaint
    let canvas = Color.skateCanvas
    let canvasSoft = Color.skateCanvasSoft
    let surfaceIceSoft = Color.skateSurfaceIceSoft
    let surfaceTealDeep = Color.skateSurfaceTealDeep
    let surfaceTealMid = Color.skateSurfaceTealMid
    let hairline = Color.skateHairline
    let hairlineDark = Color.skateHairlineDark
    let onDarkMute = Color.skateOnDarkMute
    let onDarkDim = Color.skateOnDarkDim
    let onDarkFaint = Color.skateOnDarkFaint
    let onPrimary = Color.skateOnPrimary
    let destructive = Color.skateDestructive
    let link = Color.skateLink
    let ring = Color.skateRing
    let scoreGood = Color.skateScoreGood
    let scoreMid = Color.skateScoreMid
    let scoreBad = Color.skateScoreBad
    let accentGold = Color.skateAccentGold
    let background = Color.skateCanvas
    let foreground = Color.skateInk
}

@available(iOS 15, *)
private struct SkateLabColorSchemeKey: EnvironmentKey {
    static let defaultValue = SkateLabColorScheme()
}

@available(iOS 15, *)
extension EnvironmentValues {
    var skateLabColors: SkateLabColorScheme {
        get { self[SkateLabColorSchemeKey.self] }
        set { self[SkateLabColorSchemeKey.self] = newValue }
    }
}