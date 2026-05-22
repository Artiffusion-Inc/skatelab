// AUTO-GENERATED — do not edit. Source: DESIGN.md
import SwiftUI

@available(iOS 15, *)
public struct SkateLabColorScheme {
    public var background:             Color
    public var foreground:             Color
    public var card:                   Color
    public var cardForeground:         Color
    public var popover:                Color
    public var popoverForeground:      Color
    public var primary:                Color
    public var primaryForeground:      Color
    public var secondary:              Color
    public var secondaryForeground:    Color
    public var muted:                  Color
    public var mutedForeground:        Color
    public var accent:                 Color
    public var accentForeground:       Color
    public var destructive:            Color
    public var destructiveForeground:  Color
    public var border:                 Color
    public var input:                  Color
    public var ring:                   Color

    public init(
        background:             Color = .skateCanvas,
        foreground:             Color = .skateInk,
        card:                   Color = .skateCanvas,
        cardForeground:         Color = .skateInk,
        popover:                Color = .skateCanvas,
        popoverForeground:      Color = .skateInk,
        primary:                Color = .skatePrimary,
        primaryForeground:      Color = .skatePrimaryForeground,
        secondary:              Color = .skateCanvasSoft,
        secondaryForeground:    Color = .skateInk,
        muted:                  Color = .skateCanvasSoft,
        mutedForeground:        Color = .skateInkMute,
        accent:                 Color = .skateAccentGold,
        accentForeground:       Color = .skateInk,
        destructive:            Color = .skateDestructive,
        destructiveForeground:  Color = .skatePrimaryForeground,
        border:                 Color = .skateHairline,
        input:                  Color = .skateHairline,
        ring:                   Color = .skateRing
    ) {
        self.background             = background
        self.foreground             = foreground
        self.card                   = card
        self.cardForeground         = cardForeground
        self.popover                = popover
        self.popoverForeground      = popoverForeground
        self.primary                = primary
        self.primaryForeground      = primaryForeground
        self.secondary              = secondary
        self.secondaryForeground    = secondaryForeground
        self.muted                  = muted
        self.mutedForeground        = mutedForeground
        self.accent                 = accent
        self.accentForeground       = accentForeground
        self.destructive            = destructive
        self.destructiveForeground  = destructiveForeground
        self.border                 = border
        self.input                  = input
        self.ring                   = ring
    }
}

@available(iOS 15, *)
private struct SkateLabColorsKey: EnvironmentKey {
    static let defaultValue = SkateLabColorScheme()
}

@available(iOS 15, *)
public extension EnvironmentValues {
    var skateLabColors: SkateLabColorScheme {
        get { self[SkateLabColorsKey.self] }
        set { self[SkateLabColorsKey.self] = newValue }
    }
}
