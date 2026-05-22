// AUTO-GENERATED — do not edit. Source: DESIGN.md
// Regenerate: task design:build

import SwiftUI
import CoreText

@available(iOS 15, *)
extension Font {
    private static func skateVariable(size: CGFloat, weight: Double) -> Font {
        let wghtTag = Int(2003265652) // 'wght' FourCharCode as Int
        let variation: [Int: Double] = [wghtTag: weight]
        let attrs: [CFString: Any] = [
            kCTFontNameAttribute: "InterVariable" as CFString,
            kCTFontVariationAttribute: variation as CFDictionary
        ]
        let descriptor = CTFontDescriptorCreateWithAttributes(attrs as CFDictionary)
        let ctFont = CTFontCreateWithFontDescriptor(descriptor, size, nil)
        return Font(ctFont)
    }

    // Fallback for platforms without variable font axis support
    private static func skateStatic(size: CGFloat, weight: Font.Weight) -> Font {
        switch weight {
        case .regular: return Font.custom("Inter-Regular", size: size)
        case .medium: return Font.custom("Inter-Medium", size: size)
        case .semibold: return Font.custom("Inter-SemiBold", size: size)
        case .bold: return Font.custom("Inter-Bold", size: size)
        default: return Font.custom("Inter-Medium", size: size)
        }
    }

    // Public typography tokens — uses CTFont variable axes when available
    static let skateDisplayXxl = skateVariable(size: 36, weight: 540)
    static let skateDisplayXl = skateVariable(size: 32, weight: 460)
    static let skateDisplayLg = skateVariable(size: 28, weight: 540)
    static let skateDisplayMd = skateVariable(size: 22, weight: 460)
    static let skateHeadingLg = skateVariable(size: 20, weight: 460)
    static let skateBodyLg = skateVariable(size: 18, weight: 540)
    static let skateBodyMd = skateVariable(size: 16, weight: 460)
    static let skateBodyStrong = skateVariable(size: 18.72, weight: 700)
    static let skateButtonMd = skateVariable(size: 16, weight: 700)
    static let skateButtonCap = skateVariable(size: 14, weight: 600)
    static let skateCaption = skateVariable(size: 14, weight: 460)
    static let skateMicro = skateVariable(size: 12, weight: 540)
    static let skateLegal = skateVariable(size: 11, weight: 460)
    static let skatePrice = skateVariable(size: 32, weight: 700)
}