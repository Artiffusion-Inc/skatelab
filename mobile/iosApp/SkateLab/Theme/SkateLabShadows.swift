// AUTO-GENERATED — do not edit. Source: DESIGN.md

import SwiftUI

@available(iOS 15, *)
extension View {
    /// ambient-low: 0 1px 3px rgba(0,0,0,0.08)
    /// Active tab, selected chip.
    func skateShadowAmbientLow() -> some View {
        shadow(color: .black.opacity(0.08), radius: 1.5, x: 0, y: 1)
    }

    /// ambient-medium: 0 4px 12px rgba(0,0,0,0.10)
    /// Dropdown menus, popovers.
    func skateShadowAmbientMedium() -> some View {
        shadow(color: .black.opacity(0.10), radius: 6, x: 0, y: 4)
    }

    /// ambient-high: 0 8px 24px rgba(0,0,0,0.12)
    /// Modals, floating toolbars.
    func skateShadowAmbientHigh() -> some View {
        shadow(color: .black.opacity(0.12), radius: 12, x: 0, y: 8)
    }
}