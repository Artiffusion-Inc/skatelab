// AUTO-GENERATED — do not edit. Source: DESIGN.md

import SwiftUI

// MARK: - Card Modifier

@available(iOS 15, *)
struct SkateLabCardModifier: ViewModifier {
    let backgroundColor: Color
    let foregroundColor: Color
    let cornerRadius: CGFloat
    let padding: CGFloat
    let showBorder: Bool

    init(
        backgroundColor: Color = .skateCanvas,
        foregroundColor: Color = .skateInk,
        cornerRadius: CGFloat = 16,
        padding: CGFloat = 32,
        showBorder: Bool = true
    ) {
        self.backgroundColor = backgroundColor
        self.foregroundColor = foregroundColor
        self.cornerRadius = cornerRadius
        self.padding = padding
        self.showBorder = showBorder
    }

    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(backgroundColor)
            .foregroundColor(foregroundColor)
            .cornerRadius(cornerRadius)
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(Color.skateHairline, lineWidth: showBorder ? 1 : 0)
            )
    }
}

// MARK: - Teal Band Card Modifier

@available(iOS 15, *)
struct SkateLabTealBandModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(64)
            .background(Color.skateSurfaceTealDeep)
            .foregroundColor(Color.skatePrimaryForeground)
            .cornerRadius(16)
    }
}

// MARK: - Badge Modifier

@available(iOS 15, *)
struct SkateLabBadgeModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(Color.skateSurfaceTealDeep.opacity(0.85))
            .foregroundColor(Color.skatePrimaryForeground)
            .font(.skateMicro)
            .cornerRadius(12)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.skateSurfaceIceSoft.opacity(0.4), lineWidth: 1)
            )
    }
}

// MARK: - Input Modifier

@available(iOS 15, *)
struct SkateLabInputModifier: ViewModifier {
    var isError: Bool = false

    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(Color.skateCanvas)
            .font(.skateBodyMd)
            .cornerRadius(6)
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(isError ? Color.skateDestructive : Color.skateHairline, lineWidth: 1)
            )
    }
}

// MARK: - Pill Tab Modifier

@available(iOS 15, *)
struct SkateLabPillTabModifier: ViewModifier {
    var isSelected: Bool = false

    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(isSelected ? Color.skateCanvasSoft : Color.skateCanvas)
            .foregroundColor(Color.skateInk)
            .font(.skateButtonCap)
            .cornerRadius(9999)
    }
}

// MARK: - Button Modifiers

@available(iOS 15, *)
struct SkateLabButtonPrimaryModifier: ViewModifier {
    var isPressed: Bool = false

    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(isPressed ? Color.skatePrimaryDeep : Color.skatePrimary)
            .foregroundColor(Color.skatePrimaryForeground)
            .font(.skateButtonMd)
            .cornerRadius(12)
            .scaleEffect(isPressed ? 0.98 : 1.0)
            .animation(.easeInOut(duration: 0.15), value: isPressed)
    }
}

@available(iOS 15, *)
struct SkateLabButtonOnDarkPillModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(Color.skateSurfaceIceSoft)
            .foregroundColor(Color.skatePrimary)
            .font(.skateButtonMd)
            .cornerRadius(9999)
    }
}

@available(iOS 15, *)
struct SkateLabButtonOutlineModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(Color.skateCanvas)
            .foregroundColor(Color.skateInk)
            .font(.skateButtonMd)
            .cornerRadius(12)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.skateHairlineDark, lineWidth: 1)
            )
    }
}

@available(iOS 15, *)
struct SkateLabButtonOnTealModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(Color.skateCanvas)
            .foregroundColor(Color.skateSurfaceTealDeep)
            .font(.skateButtonMd)
            .cornerRadius(12)
    }
}

@available(iOS 15, *)
struct SkateLabButtonGhostModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .foregroundColor(Color.skateInkMute)
            .font(.skateBodyMd)
            .cornerRadius(12)
    }
}

@available(iOS 15, *)
struct SkateLabButtonDestructiveModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(Color.skateDestructive.opacity(0.1))
            .foregroundColor(Color.skateDestructive)
            .font(.skateButtonMd)
            .cornerRadius(12)
    }
}

// MARK: - Metric Card Modifier

@available(iOS 15, *)
struct SkateLabMetricCardModifier: ViewModifier {
    var scoreStatus: SkateLabScoreStatus = .good

    enum SkateLabScoreStatus {
        case good, mid, bad
    }

    var scoreColor: Color {
        switch scoreStatus {
        case .good: return .skateScoreGood
        case .mid:  return .skateScoreMid
        case .bad:  return .skateScoreBad
        }
    }

    func body(content: Content) -> some View {
        content
            .padding(16)
            .background(Color.skateCanvas)
            .cornerRadius(12)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.skateHairline, lineWidth: 1)
            )
    }
}

// MARK: - Navigation Bar Modifiers

@available(iOS 15, *)
struct SkateLabNavBarDarkModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 24)
            .padding(.vertical, 16)
            .background(Color.skatePrimary)
            .foregroundColor(Color.skatePrimaryForeground)
            .font(.skateBodyMd)
            .cornerRadius(4)
    }
}

@available(iOS 15, *)
struct SkateLabNavBarLightModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 24)
            .padding(.vertical, 16)
            .background(Color.skateCanvas)
            .foregroundColor(Color.skateInk)
            .font(.skateBodyMd)
            .cornerRadius(4)
    }
}

// MARK: - Footer Modifier

@available(iOS 15, *)
struct SkateLabFooterModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 24)
            .padding(.vertical, 64)
            .background(Color.skateCanvas)
            .foregroundColor(Color.skateInkMute)
            .font(.skateCaption)
            .cornerRadius(4)
    }
}

// MARK: - Focus Ring Modifier

@available(iOS 15, *)
struct SkateLabFocusRingModifier: ViewModifier {
    var isFocused: Bool = false

    func body(content: Content) -> some View {
        content
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.skateRing.opacity(0.2), lineWidth: isFocused ? 2 : 0)
            )
            .animation(.easeOut(duration: 0.15), value: isFocused)
    }
}

// MARK: - Convenience View Extensions

@available(iOS 15, *)
extension View {
    /// Light feature card (card-feature-light)
    func skateCardFeatureLight() -> some View {
        modifier(SkateLabCardModifier())
    }

    /// Light feature card with ambient-low elevation
    func skateCardFeatureLightElevated() -> some View {
        modifier(SkateLabCardModifier())
            .skateShadowAmbientLow()
    }

    /// Teal band card (card-teal-band)
    func skateCardTealBand() -> some View {
        modifier(SkateLabTealBandModifier())
    }

    /// Opaque badge (badge-opaque)
    func skateBadgeOpaque() -> some View {
        modifier(SkateLabBadgeModifier())
    }

    /// Metric card (metric-card)
    func skateMetricCard(
        status: SkateLabMetricCardModifier.SkateLabScoreStatus = .good
    ) -> some View {
        modifier(SkateLabMetricCardModifier(scoreStatus: status))
    }

    /// Pill tab (pill-tab-light)
    func skatePillTab(isSelected: Bool = false) -> some View {
        modifier(SkateLabPillTabModifier(isSelected: isSelected))
    }

    /// Primary dark button (button-primary-dark)
    func skateButtonPrimary(isPressed: Bool = false) -> some View {
        modifier(SkateLabButtonPrimaryModifier(isPressed: isPressed))
    }

    /// On-dark pill button (button-on-dark-pill) — hero only
    func skateButtonOnDarkPill() -> some View {
        modifier(SkateLabButtonOnDarkPillModifier())
    }

    /// Secondary outline button (button-secondary-outline)
    func skateButtonOutline() -> some View {
        modifier(SkateLabButtonOutlineModifier())
    }

    /// On-teal button (button-on-teal)
    func skateButtonOnTeal() -> some View {
        modifier(SkateLabButtonOnTealModifier())
    }

    /// Ghost button (button-ghost)
    func skateButtonGhost() -> some View {
        modifier(SkateLabButtonGhostModifier())
    }

    /// Destructive button (button-destructive)
    func skateButtonDestructive() -> some View {
        modifier(SkateLabButtonDestructiveModifier())
    }

    /// Text input styling (text-input)
    func skateTextInput(isError: Bool = false) -> some View {
        modifier(SkateLabInputModifier(isError: isError))
    }

    /// Dark navigation bar (nav-bar-dark)
    func skateNavBarDark() -> some View {
        modifier(SkateLabNavBarDarkModifier())
    }

    /// Light navigation bar (nav-bar-light)
    func skateNavBarLight() -> some View {
        modifier(SkateLabNavBarLightModifier())
    }

    /// Footer (footer-light)
    func skateFooterLight() -> some View {
        modifier(SkateLabFooterModifier())
    }

    /// Focus ring (ring)
    func skateFocusRing(isFocused: Bool = false) -> some View {
        modifier(SkateLabFocusRingModifier(isFocused: isFocused))
    }

    /// Popover with ambient-medium elevation
    func skatePopoverElevated() -> some View {
        background(Color.skateCanvas)
            .cornerRadius(12)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.skateHairline, lineWidth: 1)
            )
            .skateShadowAmbientMedium()
    }

    /// Modal with ambient-high elevation
    func skateModalElevated() -> some View {
        background(Color.skateCanvas)
            .cornerRadius(16)
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(Color.skateHairline, lineWidth: 1)
            )
            .skateShadowAmbientHigh()
    }
}