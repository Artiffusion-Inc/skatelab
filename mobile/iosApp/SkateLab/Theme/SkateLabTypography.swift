// AUTO-GENERATED — do not edit. Source: DESIGN.md
import SwiftUI
import CoreText

@available(iOS 15, *)
public extension Font {

    // MARK: - Private helpers

    /// Attempt to create a variable-weight font via CTFont variation axis.
    private static func skateVariable(size: CGFloat, weight: CGFloat) -> Font {
        guard let uiFont = UIFont(name: "InterVariable", size: size)
                ?? UIFont(name: "Inter-V", size: size)
                ?? UIFont(name: "Inter", size: size) else {
            return skateStatic(size: size, weight: weight)
        }
        let ctFont = CTFontCreateWithFontDescriptor(uiFont.fontDescriptor as CTFontDescriptor, size, nil)
        let axisID = Int(0x77676874) // 'wght'
        let variation: [String: Any] = [
            kCTFontVariationAttribute as String: [axisID: Double(weight)]
        ]
        guard let varied = CTFontCreateCopyWithAttributes(ctFont, size, nil, variation as CFDictionary) else {
            return skateStatic(size: size, weight: weight)
        }
        return Font(varied as UIFont)
    }

    /// Static system-font fallback preserving weight class.
    private static func skateStatic(size: CGFloat, weight: CGFloat) -> Font {
        let systemWeight: Font.Weight
        switch Int(weight) {
        case ..<400:  systemWeight = .light
        case ..<460:  systemWeight = .regular
        case ..<540:  systemWeight = .medium
        case ..<600:  systemWeight = .semibold
        case ..<700:  systemWeight = .bold
        default:      systemWeight = .heavy
        }
        return .system(size: size, weight: systemWeight, design: .default)
    }

    // MARK: - Typography tokens

    static var skateDisplayXxl:  Font { skateVariable(size: 64,    weight: 540) }
    static var skateDisplayXl:   Font { skateVariable(size: 48,    weight: 460) }
    static var skateDisplayLg:   Font { skateVariable(size: 28,    weight: 540) }
    static var skateDisplayMd:   Font { skateVariable(size: 22,    weight: 460) }
    static var skateHeadingLg:   Font { skateVariable(size: 20,    weight: 460) }
    static var skateBodyLg:      Font { skateVariable(size: 18,    weight: 540) }
    static var skateBodyMd:      Font { skateVariable(size: 16,    weight: 460) }
    static var skateBodyStrong:  Font { skateVariable(size: 18.72, weight: 700) }
    static var skateButtonMd:    Font { skateVariable(size: 16,    weight: 700) }
    static var skateButtonCap:   Font { skateVariable(size: 14,    weight: 600) }
    static var skateCaption:     Font { skateVariable(size: 14,    weight: 460) }
    static var skateMicro:       Font { skateVariable(size: 12,    weight: 540) }
    static var skateLegal:       Font { skateVariable(size: 11,    weight: 460) }
    static var skatePrice:       Font { skateVariable(size: 48,    weight: 700) }
}
