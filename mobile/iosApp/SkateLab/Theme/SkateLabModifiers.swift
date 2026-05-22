// AUTO-GENERATED — do not edit. Source: DESIGN.md
import SwiftUI

// MARK: - Card Modifier
@available(iOS 15, *)
public struct SkateLabCardModifier: ViewModifier {
    public enum Style {
        case featureLight
        case tealBand
    }

    let style: Style

    public func body(content: Content) -> some View {
        switch style {
        case .featureLight:
            content
                .padding(32)
                .background(Color.skateCanvas)
                .foregroundColor(Color.skateInk)
                .cornerRadius(16)
                .font(.skateBodyMd)
        case .tealBand:
            content
                .padding(64)
                .background(Color.skateSurfaceTealDeep)
                .foregroundColor(Color.skatePrimaryForeground)
                .cornerRadius(16)
                .font(.skateBodyLg)
        }
    }
}

// MARK: - Badge Modifier
@available(iOS 15, *)
public struct SkateLabBadgeModifier: ViewModifier {
    public func body(content: Content) -> some View {
        content
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(Color.skatePrimaryDeep.opacity(0.85))
            .foregroundColor(Color.skatePrimaryForeground)
            .cornerRadius(12)
            .font(.skateMicro)
    }
}

// MARK: - Button Modifier
@available(iOS 15, *)
public struct SkateLabButtonModifier: ViewModifier {
    public enum Style {
        case primaryDark
        case primaryDarkPressed
        case onDarkPill
        case secondaryOutline
        case onTeal
        case ghost
    }

    let style: Style

    public func body(content: Content) -> some View {
        switch style {
        case .primaryDark:
            content
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(Color.skatePrimary)
                .foregroundColor(Color.skatePrimaryForeground)
                .cornerRadius(12)
                .font(.skateButtonMd)
        case .primaryDarkPressed:
            content
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(Color.skatePrimaryDeep)
                .foregroundColor(Color.skatePrimaryForeground)
                .cornerRadius(12)
                .font(.skateButtonMd)
        case .onDarkPill:
            content
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(Color.skateSurfaceIceSoft)
                .foregroundColor(Color.skatePrimary)
                .clipShape(Capsule())
                .font(.skateButtonMd)
        case .secondaryOutline:
            content
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(Color.skateCanvas)
                .foregroundColor(Color.skateInk)
                .cornerRadius(12)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(Color.skateHairlineDark, lineWidth: 1)
                )
                .font(.skateButtonMd)
        case .onTeal:
            content
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(Color.skateCanvas)
                .foregroundColor(Color.skateSurfaceTealDeep)
                .cornerRadius(12)
                .font(.skateButtonMd)
        case .ghost:
            content
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .foregroundColor(Color.skateInkMute)
                .cornerRadius(12)
                .font(.skateBodyMd)
        }
    }
}

// MARK: - Input Modifier
@available(iOS 15, *)
public struct SkateLabInputModifier: ViewModifier {
    public func body(content: Content) -> some View {
        content
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(Color.skateCanvas)
            .foregroundColor(Color.skateInk)
            .cornerRadius(6)
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(Color.skateHairline, lineWidth: 1)
            )
            .font(.skateBodyMd)
    }
}

// MARK: - Pill Tab Modifier
@available(iOS 15, *)
public struct SkateLabPillTabModifier: ViewModifier {
    public func body(content: Content) -> some View {
        content
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(Color.skateCanvas)
            .foregroundColor(Color.skateInk)
            .clipShape(Capsule())
            .font(.skateButtonCap)
    }
}

// MARK: - Nav Bar Modifier
@available(iOS 15, *)
public struct SkateLabNavBarModifier: ViewModifier {
    public enum Style {
        case dark
        case light
    }

    let style: Style

    public func body(content: Content) -> some View {
        switch style {
        case .dark:
            content
                .padding(.horizontal, 24)
                .padding(.vertical, 16)
                .background(Color.skatePrimary)
                .foregroundColor(Color.skatePrimaryForeground)
                .cornerRadius(4)
                .font(.skateBodyMd)
        case .light:
            content
                .padding(.horizontal, 24)
                .padding(.vertical, 16)
                .background(Color.skateCanvas)
                .foregroundColor(Color.skateInk)
                .cornerRadius(4)
                .font(.skateBodyMd)
        }
    }
}

// MARK: - Footer Modifier
@available(iOS 15, *)
public struct SkateLabFooterModifier: ViewModifier {
    public func body(content: Content) -> some View {
        content
            .padding(.horizontal, 24)
            .padding(.vertical, 64)
            .background(Color.skateCanvas)
            .foregroundColor(Color.skateInkMute)
            .cornerRadius(4)
            .font(.skateCaption)
    }
}

// MARK: - Convenience View Extensions
@available(iOS 15, *)
public extension View {
    func skateCard(style: SkateLabCardModifier.Style) -> some View {
        modifier(SkateLabCardModifier(style: style))
    }

    func skateBadge() -> some View {
        modifier(SkateLabBadgeModifier())
    }

    func skateButton(style: SkateLabButtonModifier.Style) -> some View {
        modifier(SkateLabButtonModifier(style: style))
    }

    func skateInput() -> some View {
        modifier(SkateLabInputModifier())
    }

    func skatePillTab() -> some View {
        modifier(SkateLabPillTabModifier())
    }

    func skateNavBar(style: SkateLabNavBarModifier.Style) -> some View {
        modifier(SkateLabNavBarModifier(style: style))
    }

    func skateFooter() -> some View {
        modifier(SkateLabFooterModifier())
    }

    /// Combines a feature-light card with an ambient-medium shadow for floating overlays.
    func skateFloatingCard() -> some View {
        self
            .skateCard(style: .featureLight)
            .skateAmbientMediumShadow()
    }

    /// Applies the standard focus ring treatment using SkateLabColors.
    func skateFocusRing() -> some View {
        self.overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.skateRing, lineWidth: 2)
                .padding(-4)
        )
    }
}
