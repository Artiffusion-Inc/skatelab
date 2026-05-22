// AUTO-GENERATED — do not edit. Source: DESIGN.md
import SwiftUI

@available(iOS 15, *)
public struct SkateLabColorScheme {
    public let primary: Color
    public let primaryDeep: Color
    public let primaryForeground: Color
    public let ink: Color
    public let inkMute: Color
    public let inkFaint: Color
    public let canvas: Color
    public let canvasSoft: Color
    public let surfaceIceSoft: Color
    public let surfaceTealDeep: Color
    public let surfaceTealMid: Color
    public let hairline: Color
    public let hairlineDark: Color
    public let onDarkMute: Color
    public let onDarkDim: Color
    public let onDarkFaint: Color
    public let destructive: Color
    public let link: Color
    public let ring: Color
    public let scoreGood: Color
    public let scoreMid: Color
    public let scoreBad: Color
    public let accentGold: Color
    public let onPrimary: Color
    public let background: Color
    public let foreground: Color
    public let card: Color
    public let cardForeground: Color
    public let popover: Color
    public let popoverForeground: Color
    public let secondary: Color
    public let secondaryForeground: Color
    public let muted: Color
    public let mutedForeground: Color
    public let accent: Color
    public let accentForeground: Color
    public let destructiveForeground: Color
    public let border: Color
    public let input: Color
}

@available(iOS 15, *)
private struct SkateLabColorSchemeKey: EnvironmentKey {
    static let defaultValue: SkateLabColorScheme = .skateLabDefault
}

@available(iOS 15, *)
public extension EnvironmentValues {
    var skateLabColors: SkateLabColorScheme {
        get { self[SkateLabColorSchemeKey.self] }
        set { self[SkateLabColorSchemeKey.self] = newValue }
    }
}

@available(iOS 15, *)
public extension SkateLabColorScheme {
    static let skateLabDefault = SkateLabColorScheme(
        primary: .skatePrimary,
        primaryDeep: .skatePrimaryDeep,
        primaryForeground: .skatePrimaryForeground,
        ink: .skateInk,
        inkMute: .skateInkMute,
        inkFaint: .skateInkFaint,
        canvas: .skateCanvas,
        canvasSoft: .skateCanvasSoft,
        surfaceIceSoft: .skateSurfaceIceSoft,
        surfaceTealDeep: .skateSurfaceTealDeep,
        surfaceTealMid: .skateSurfaceTealMid,
        hairline: .skateHairline,
        hairlineDark: .skateHairlineDark,
        onDarkMute: .skateOnDarkMute,
        onDarkDim: .skateOnDarkDim,
        onDarkFaint: .skateOnDarkFaint,
        destructive: .skateDestructive,
        link: .skateLink,
        ring: .skateRing,
        scoreGood: .skateScoreGood,
        scoreMid: .skateScoreMid,
        scoreBad: .skateScoreBad,
        accentGold: .skateAccentGold,
        onPrimary: .skateOnPrimary,
        background: .skateBackground,
        foreground: .skateForeground,
        card: .skateCard,
        cardForeground: .skateCardForeground,
        popover: .skatePopover,
        popoverForeground: .skatePopoverForeground,
        secondary: .skateSecondary,
        secondaryForeground: .skateSecondaryForeground,
        muted: .skateMuted,
        mutedForeground: .skateMutedForeground,
        accent: .skateAccent,
        accentForeground: .skateAccentForeground,
        destructiveForeground: .skateDestructiveForeground,
        border: .skateBorder,
        input: .skateInput
    )
}