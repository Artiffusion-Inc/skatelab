// AUTO-GENERATED — do not edit. Source: DESIGN.md

import SwiftUI

@available(iOS 15, *)
struct SkateLabColorScheme {
    // MARK: - Brand & Accent
    let primary = Color.skatePrimary
    let primaryDeep = Color.skatePrimaryDeep
    let primaryForeground = Color.skatePrimaryForeground

    // MARK: - Text
    let ink = Color.skateInk
    let inkMute = Color.skateInkMute
    let inkFaint = Color.skateInkFaint

    // MARK: - Surface
    let canvas = Color.skateCanvas
    let canvasSoft = Color.skateCanvasSoft
    let surfaceIceSoft = Color.skateSurfaceIceSoft
    let surfaceTealDeep = Color.skateSurfaceTealDeep
    let surfaceTealMid = Color.skateSurfaceTealMid

    // MARK: - Border
    let hairline = Color.skateHairline
    let hairlineDark = Color.skateHairlineDark

    // MARK: - On Dark
    let onDarkMute = Color.skateOnDarkMute
    let onDarkDim = Color.skateOnDarkDim
    let onDarkFaint = Color.skateOnDarkFaint

    // MARK: - Semantic
    let destructive = Color.skateDestructive
    let link = Color.skateLink
    let ring = Color.skateRing
    let scoreGood = Color.skateScoreGood
    let scoreMid = Color.skateScoreMid
    let scoreBad = Color.skateScoreBad
    let accentGold = Color.skateAccentGold

    // MARK: - Semantic Aliases
    let onPrimary = Color.skateOnPrimary
    let background = Color.skateBackground
    let foreground = Color.skateForeground
    let card = Color.skateCard
    let cardForeground = Color.skateCardForeground
    let popover = Color.skatePopover
    let popoverForeground = Color.skatePopoverForeground
    let secondary = Color.skateSecondary
    let secondaryForeground = Color.skateSecondaryForeground
    let muted = Color.skateMuted
    let mutedForeground = Color.skateMutedForeground
    let accent = Color.skateAccent
    let accentForeground = Color.skateAccentForeground
    let destructiveForeground = Color.skateDestructiveForeground
    let border = Color.skateBorder
    let input = Color.skateInput

    // MARK: - Chart
    let chart1 = Color.skateChart1
    let chart2 = Color.skateChart2
    let chart3 = Color.skateChart3
    let chart4 = Color.skateChart4
    let chart5 = Color.skateChart5

    // MARK: - Sidebar
    let sidebarBackground = Color.skateSidebarBackground
    let sidebarForeground = Color.skateSidebarForeground
    let sidebarPrimary = Color.skateSidebarPrimary
    let sidebarPrimaryForeground = Color.skateSidebarPrimaryForeground
    let sidebarAccent = Color.skateSidebarAccent
    let sidebarAccentForeground = Color.skateSidebarAccentForeground
    let sidebarBorder = Color.skateSidebarBorder
    let sidebarRing = Color.skateSidebarRing
}

// MARK: - Environment

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