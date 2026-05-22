// AUTO-GENERATED — do not edit. Source: DESIGN.md

import SwiftUI
import CoreText

@available(iOS 15, *)
extension Font {
    // MARK: - Variable Font Helpers

    /// Creates an Inter Variable font at a custom weight axis value.
    /// Uses CTFontDescriptorCreateCopyWithVariation to set the `wght` axis.
    private static func skateVariable(size: CGFloat, weight: CGFloat) -> Font {
        let baseDescriptor = CTFontDescriptorCreateWithAttributes(
            [kCTFontFamilyName: "Inter" as CFString,
             kCTFontSize: size as CFNumber] as CFDictionary
        )

        // 'wght' axis tag in big-endian: 0x77676874
        let wghtAxis: UInt32 = 0x7767_6874
        let variedDescriptor = CTFontDescriptorCreateCopyWithVariation(
            baseDescriptor,
            wghtAxis,
            Float64(weight)
        )
        let ctFont = CTFontCreateWithFontDescriptor(variedDescriptor, size, nil)
        return Font(ctFont)
    }

    /// Fallback using the closest standard SwiftUI weight when Inter Variable
    /// is unavailable on the system.
    private static func skateStatic(size: CGFloat, weight: CGFloat) -> Font {
        let base = Font.system(size: size, design: .default)
        switch weight {
        case ..<450:   return base.weight(.regular)
        case 450..<550: return base.weight(.medium)
        case 550..<650: return base.weight(.semibold)
        case 650..<750: return base.weight(.bold)
        default:        return base.weight(.bold)
        }
    }

    // MARK: - Display

    /// display-xxl · Hero headline
    /// Size: clamp(2.25rem, 5.5vw, 4rem) → 48pt on iOS
    /// Weight: 540 · Line height: 0.96 · Tracking: 0
    static var skateDisplayXxl: Font {
        skateVariable(size: 48, weight: 540)
    }

    /// display-xl · Section opener on light
    /// Size: clamp(2rem, 4vw, 3rem) → 36pt on iOS
    /// Weight: 460 · Line height: 0.96 · Tracking: -1.32pt
    static var skateDisplayXl: Font {
        skateVariable(size: 36, weight: 460)
    }

    /// display-lg · Sub-section / closing CTA headline
    /// Size: 28pt · Weight: 540 · Line height: 1.14 · Tracking: -0.63pt
    static var skateDisplayLg: Font {
        skateVariable(size: 28, weight: 540)
    }

    /// display-md · Card title
    /// Size: 22pt · Weight: 460 · Line height: 1.1 · Tracking: -0.315pt
    static var skateDisplayMd: Font {
        skateVariable(size: 22, weight: 460)
    }

    // MARK: - Heading

    /// heading-lg · Compact card title, FAQ question, auth heading
    /// Size: 20pt · Weight: 460 · Line height: 1.2 · Tracking: -0.4pt
    static var skateHeadingLg: Font {
        skateVariable(size: 20, weight: 460)
    }

    // MARK: - Body

    /// body-lg · Marketing body lead
    /// Size: 18pt · Weight: 540 · Line height: 1.5 · Tracking: -0.135pt
    static var skateBodyLg: Font {
        skateVariable(size: 18, weight: 540)
    }

    /// body-md · Default UI body
    /// Size: 16pt · Weight: 460 · Line height: 1.5 · Tracking: 0
    static var skateBodyMd: Font {
        skateVariable(size: 16, weight: 460)
    }

    /// body-strong · Emphasized body (weight 700)
    /// Size: 18.72pt ≈ 19pt · Weight: 700 · Line height: 1.5 · Tracking: 0
    static var skateBodyStrong: Font {
        skateVariable(size: 19, weight: 700)
    }

    // MARK: - Button

    /// button-md · Primary button label
    /// Size: 16pt · Weight: 700 · Line height: 1.0 · Tracking: 0
    static var skateButtonMd: Font {
        skateVariable(size: 16, weight: 700)
    }

    /// button-cap · Compact button label, badge text
    /// Size: 14pt · Weight: 600 · Line height: 1.0 · Tracking: 0
    static var skateButtonCap: Font {
        skateVariable(size: 14, weight: 600)
    }

    // MARK: - Small

    /// caption · Helper, footnote, metadata
    /// Size: 14pt · Weight: 460 · Line height: 1.4 · Tracking: 0
    static var skateCaption: Font {
        skateVariable(size: 14, weight: 460)
    }

    /// micro · Pill label, fine print, eyebrow
    /// Size: 12pt · Weight: 540 · Line height: 1.4 · Tracking: 0
    static var skateMicro: Font {
        skateVariable(size: 12, weight: 540)
    }

    /// legal · Copyright, terms
    /// Size: 11pt · Weight: 460 · Line height: 1.5 · Tracking: 0
    static var skateLegal: Font {
        skateVariable(size: 11, weight: 460)
    }

    /// price · Pricing display (tabular-nums)
    /// Size: clamp(2.25rem, 4vw, 3rem) → 36pt on iOS
    /// Weight: 700 · Line height: 1.0 · Tracking: -0.03em ≈ -1.08pt
    static var skatePrice: Font {
        skateVariable(size: 36, weight: 700)
    }
}

// MARK: - Typography View Modifiers

@available(iOS 15, *)
extension View {
    /// display-xxl: tight 0.96 line-height, no tracking
    func skateDisplayXxlStyle() -> some View {
        font(.skateDisplayXxl)
            .lineSpacing(-1.92)
            .tracking(0)
    }

    /// display-xl: tight 0.96 line-height, -1.32pt tracking
    func skateDisplayXlStyle() -> some View {
        font(.skateDisplayXl)
            .lineSpacing(-1.44)
            .tracking(-1.32)
    }

    /// display-lg: 1.14 line-height, -0.63pt tracking
    func skateDisplayLgStyle() -> some View {
        font(.skateDisplayLg)
            .lineSpacing(3.92)
            .tracking(-0.63)
    }

    /// display-md: 1.1 line-height, -0.315pt tracking
    func skateDisplayMdStyle() -> some View {
        font(.skateDisplayMd)
            .lineSpacing(2.2)
            .tracking(-0.315)
    }

    /// heading-lg: 1.2 line-height, -0.4pt tracking
    func skateHeadingLgStyle() -> some View {
        font(.skateHeadingLg)
            .lineSpacing(4)
            .tracking(-0.4)
    }

    /// body-lg: 1.5 line-height, -0.135pt tracking
    func skateBodyLgStyle() -> some View {
        font(.skateBodyLg)
            .lineSpacing(9)
            .tracking(-0.135)
    }

    /// body-md: 1.5 line-height, no tracking
    func skateBodyMdStyle() -> some View {
        font(.skateBodyMd)
            .lineSpacing(8)
    }

    /// body-strong: 1.5 line-height, no tracking
    func skateBodyStrongStyle() -> some View {
        font(.skateBodyStrong)
            .lineSpacing(9.5)
    }

    /// button-md: 1.0 line-height, no tracking
    func skateButtonMdStyle() -> some View {
        font(.skateButtonMd)
    }

    /// button-cap: 1.0 line-height, no tracking
    func skateButtonCapStyle() -> some View {
        font(.skateButtonCap)
    }

    /// caption: 1.4 line-height, no tracking
    func skateCaptionStyle() -> some View {
        font(.skateCaption)
            .lineSpacing(5.6)
    }

    /// micro: 1.4 line-height, no tracking
    func skateMicroStyle() -> some View {
        font(.skateMicro)
            .lineSpacing(4.8)
    }

    /// legal: 1.5 line-height, no tracking
    func skateLegalStyle() -> some View {
        font(.skateLegal)
            .lineSpacing(5.5)
    }

    /// price: 1.0 line-height, -0.03em tracking, tabular-nums
    func skatePriceStyle() -> some View {
        font(.skatePrice)
            .tracking(-1.08)
            .monospacedDigit()
    }
}