// AUTO-GENERATED — do not edit. Source: DESIGN.md
import SwiftUI

@available(iOS 15, *)
public extension View {
    func skateAmbientLowShadow() -> some View {
        shadow(color: Color.black.opacity(0.08), radius: 3, x: 0, y: 1)
    }

    func skateAmbientMediumShadow() -> some View {
        shadow(color: Color.black.opacity(0.10), radius: 12, x: 0, y: 4)
    }

    func skateAmbientHighShadow() -> some View {
        shadow(color: Color.black.opacity(0.12), radius: 24, x: 0, y: 8)
    }
}