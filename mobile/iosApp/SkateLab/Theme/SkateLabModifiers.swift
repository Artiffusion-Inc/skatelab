// AUTO-GENERATED — do not edit. Source: DESIGN.md
import SwiftUI

@available(iOS 15, *)
public struct SkateLabCardModifier: ViewModifier {
    let background: Color
    let cornerRadius: CGFloat
    let padding: EdgeInsets

    public init(
        background: Color = .skateCanvas,
        cornerRadius: CGFloat = 16,
        padding: EdgeInsets = EdgeInsets(top: 32, leading: 32, bottom: 32, trailing: 32)
    ) {
        self.background = background
        self.cornerRadius = cornerRadius
        self.padding = padding
    }

    public func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(background)
            .cornerRadius(cornerRadius)
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(Color.skateHairline, lineWidth: 1)
            )
    }
}

@available(iOS 15, *)
public struct SkateLabBadgeModifier: ViewModifier {
    let background: Color
    let textColor: Color
    let cornerRadius: CGFloat
    let padding: EdgeInsets

    public init(
        background: Color = .skatePrimaryDeep.opacity(0.85),
        textColor: Color = .skatePrimaryForeground,
        cornerRadius: CGFloat = 12,
        padding: EdgeInsets = EdgeInsets(top: 12, leading: 16, bottom: 12, trailing: 16)
    ) {
        self.background = background
        self.textColor = textColor
        self.cornerRadius = cornerRadius
        self.padding = padding
    }

    public func body(content: Content) -> some View {
        content
            .foregroundColor(textColor)
            .font(.skateMicro)
            .padding(padding)
            .background(background)
            .cornerRadius(cornerRadius)
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(Color.skateSurfaceIceSoft.opacity(0.4), lineWidth: 1)
            )
    }
}

@available(iOS 15, *)
public struct SkateLabButtonModifier: ViewModifier {
    let background: Color
    let textColor: Color
    let cornerRadius: CGFloat
    let padding: EdgeInsets

    public init(
        background: Color,
        textColor: Color,
        cornerRadius: CGFloat = 12,
        padding: EdgeInsets = EdgeInsets(top: 12, leading: 20, bottom: 12, trailing: 20)
    ) {
        self.background = background
        self.textColor = textColor
        self.cornerRadius = cornerRadius
        self.padding = padding
    }

    public func body(content: Content) -> some View {
        content
            .foregroundColor(textColor)
            .padding(padding)
            .background(background)
            .cornerRadius(cornerRadius)
    }
}

@available(iOS 15, *)
public struct SkateLabTextInputModifier: ViewModifier {
    public func body(content: Content) -> some View {
        content
            .font(.skateBodyMd)
            .foregroundColor(.skateInk)
            .padding(EdgeInsets(top: 10, leading: 12, bottom: 10, trailing: 12))
            .background(.skateCanvas)
            .cornerRadius(6)
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(Color.skateHairline, lineWidth: 1)
            )
    }
}

@available(iOS 15, *)
public extension View {
    func skateCardFeatureLight() -> some View {
        modifier(SkateLabCardModifier(
            background: .skateCanvas,
            cornerRadius: 16,
            padding: EdgeInsets(top: 32, leading: 32, bottom: 32, trailing: 32)
        ))
    }

    func skateCardTealBand() -> some View {
        modifier(SkateLabCardModifier(
            background: .skateSurfaceTealDeep,
            cornerRadius: 16,
            padding: EdgeInsets(top: 64, leading: 64, bottom: 64, trailing: 64)
        ))
    }

    func skateBadgeOpaque() -> some View {
        modifier(SkateLabBadgeModifier())
    }

    func skateButtonPrimaryDark() -> some View {
        self
            .font(.skateButtonMd)
            .modifier(SkateLabButtonModifier(
                background: .skatePrimary,
                textColor: .skatePrimaryForeground,
                cornerRadius: 12
            ))
    }

    func skateButtonPrimaryDarkPressed() -> some View {
        self
            .font(.skateButtonMd)
            .modifier(SkateLabButtonModifier(
                background: .skatePrimaryDeep,
                textColor: .skatePrimaryForeground,
                cornerRadius: 12
            ))
    }

    func skateButtonOnDarkPill() -> some View {
        self
            .font(.skateButtonMd)
            .modifier(SkateLabButtonModifier(
                background: .skateSurfaceIceSoft,
                textColor: .skatePrimary,
                cornerRadius: 9999
            ))
    }

    func skateButtonSecondaryOutline() -> some View {
        self
            .font(.skateButtonMd)
            .modifier(SkateLabButtonModifier(
                background: .skateCanvas,
                textColor: .skateInk,
                cornerRadius: 12
            ))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.skateHairlineDark, lineWidth: 1)
            )
    }

    func skateButtonOnTeal() -> some View {
        self
            .font(.skateButtonMd)
            .modifier(SkateLabButtonModifier(
                background: .skateCanvas,
                textColor: .skateSurfaceTealDeep,
                cornerRadius: 12
            ))
    }

    func skateButtonGhost() -> some View {
        self
            .font(.skateBodyMd)
            .modifier(SkateLabButtonModifier(
                background: .clear,
                textColor: .skateInkMute,
                cornerRadius: 12
            ))
    }

    func skateButtonDestructive() -> some View {
        self
            .font(.skateButtonMd)
            .modifier(SkateLabButtonModifier(
                background: .skateDestructive.opacity(0.1),
                textColor: .skateDestructive,
                cornerRadius: 12
            ))
    }

    func skateTextInput() -> some View {
        modifier(SkateLabTextInputModifier())
    }

    func skatePillTabLight() -> some View {
        self
            .font(.skateButtonCap)
            .modifier(SkateLabButtonModifier(
                background: .skateCanvas,
                textColor: .skateInk,
                cornerRadius: 9999,
                padding: EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16)
            ))
    }

    func skateNavBarDark() -> some View {
        modifier(SkateLabCardModifier(
            background: .skatePrimary,
            cornerRadius: 4,
            padding: EdgeInsets(top: 16, leading: 24, bottom: 16, trailing: 24)
        ))
    }

    func skateNavBarLight() -> some View {
        modifier(SkateLabCardModifier(
            background: .skateCanvas,
            cornerRadius: 4,
            padding: EdgeInsets(top: 16, leading: 24, bottom: 16, trailing: 24)
        ))
    }

    func skateFooterLight() -> some View {
        modifier(SkateLabCardModifier(
            background: .skateCanvas,
            cornerRadius: 4,
            padding: EdgeInsets(top: 64, leading: 24, bottom: 64, trailing: 24)
        ))
    }
}