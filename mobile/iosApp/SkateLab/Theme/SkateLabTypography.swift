// AUTO-GENERATED — do not edit. Source: DESIGN.md
import SwiftUI
import CoreText

@available(iOS 15, *)
private func skateVariable(size: CGFloat, weight: CGFloat) -> Font {
    let fontAttributes: [CFString: Any] = [
        kCTFontNameAttribute: "Inter" as CFString,
        kCTFontSizeAttribute: size,
        kCTFontVariationAttribute: [2003265652: weight]
    ]
    let descriptor = CTFontDescriptorCreateWithAttributes(fontAttributes as CFDictionary)
    guard let ctFont = CTFontCreateWithFontDescriptor(descriptor, size, nil) else {
        return skateStatic(size: size, weight: weight)
    }
    return Font(ctFont as CTFont)
}

@available(iOS 15, *)
private func skateStatic(size: CGFloat, weight: CGFloat) -> Font {
    if weight >= 700 {
        return .custom("Inter-Bold", size: size)
    } else if weight >= 600 {
        return .custom("Inter-SemiBold", size: size)
    } else if weight >= 500 {
        return .custom("Inter-Medium", size: size)
    } else {
        return .custom("Inter-Regular", size: size)
    }
}

@available(iOS 15, *)
public extension Font {
    static var skateDisplayXxl: Font { skateVariable(size: 64, weight: 540) }
    static var skateDisplayXl: Font { skateVariable(size: 48, weight: 460) }
    static var skateDisplayLg: Font { skateVariable(size: 28, weight: 540) }
    static var skateDisplayMd: Font { skateVariable(size: 22, weight: 460) }
    static var skateHeadingLg: Font { skateVariable(size: 20, weight: 460) }
    static var skateBodyLg: Font { skateVariable(size: 18, weight: 540) }
    static var skateBodyMd: Font { skateVariable(size: 16, weight: 460) }
    static var skateBodyStrong: Font { skateVariable(size: 18.72, weight: 700) }
    static var skateButtonMd: Font { skateVariable(size: 16, weight: 700) }
    static var skateButtonCap: Font { skateVariable(size: 14, weight: 600) }
    static var skateCaption: Font { skateVariable(size: 14, weight: 460) }
    static var skateMicro: Font { skateVariable(size: 12, weight: 540) }
    static var skateLegal: Font { skateVariable(size: 11, weight: 460) }
    static var skatePrice: Font { skateVariable(size: 48, weight: 700) }
}